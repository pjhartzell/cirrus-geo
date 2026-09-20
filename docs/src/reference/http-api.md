# HTTP API

The [`api`](lambda-functions.md#api) Lambda function serves a read-only HTTP API over the [state database](state-database.md) and workflow event metrics. `cloudformation/core/api.yaml` fronts it with an Amazon API Gateway REST API. There is no Lambda function URL. All handler logic is in `src/cirrus/lambda_functions/api.py`.

## URL structure

The REST API has a `GET` method on the root resource and a `GET` method on a `{proxy+}` resource, both integrated with the function as `AWS_PROXY`. It is deployed to a single stage named `dev`, so the invoke URL is:

```text
https://<api-id>.execute-api.<region>.amazonaws.com/dev/<path>
```

Both `core/api.yaml` and `main.yaml` expose the invoke URL and API ID as the `ApiGatewayUrl` and `ApiGatewayId` outputs. Authorization is `NONE` on both methods, so the API is unauthenticated. API Gateway rejects any verb other than `GET` before the function is invoked.

## Path handling

`lambda_handler` splits the request path on `/`, drops empty segments, and drops a leading segment equal to the stage name. The remaining segments are rejoined with `/` and matched against the routes below. Paths in this page are written as they appear after the stage.

## Routes

Every route responds to `GET` with a JSON body. Every response, including errors, carries `Access-Control-Allow-Origin: *` and `Access-Control-Allow-Credentials: true`.

| Path | Returns |
| --- | --- |
| `/` | A catalog-like root with links to each collections-workflow summary |
| `/stats` | Aggregate workflow-event counts by state: daily, hourly, and rolling hour |
| `/<collections>/workflow-<workflow>` | Per-state record counts for one collections-workflow |
| `/<collections>/workflow-<workflow>/items` | A page of state database records for one collections-workflow |
| `/<collections>/workflow-<workflow>/<itemids>` | The state database record for one payload ID |

Dispatch is a sequence of checks on the rejoined path rather than a router:

1. An empty path is the root.
2. `stats` is the stats route.
3. A path without the substring `/workflow-` returns 400.
4. Anything else is parsed by `StateDB.payload_id_to_key`, which splits on `/workflow-` and then splits the remainder on its first `/`. An empty item-ID part is the summary route, the literal `items` is the page route, and any other value is looked up as a payload ID.

Because the page route is selected by the literal string `items`, a payload whose item-ID segment is exactly `items` cannot be fetched through the single-record route.

## Query parameters

Parsed once per request and applied to the summary and page routes.

| Parameter | Applies to | Default | Notes |
| --- | --- | --- | --- |
| `state` | summary, page | unfiltered | One of `PROCESSING`, `SUCCEEDED`, `FAILED`, `INVALID`, `ABORTED`, `CLAIMED` |
| `since` | summary, page | unfiltered | Look-back window: an integer immediately followed by `d`, `h`, or `m`, for example `10d`. Any other form raises an unhandled `ValueError` |
| `limit` | summary, page | `100000` | Cast with `int()`. A non-integer raises an unhandled `ValueError`. On the summary route, a count above `limit` is reported as the string `"<limit>+"` |
| `nextkey` | page | none | The `payload_id` of the last record in the previous page |
| `sort_ascending` | page | `0` | Parsed as `bool(int(...))`. `1` sorts ascending |
| `sort_index` | page | `updated` | Passed to `StateDB.query`. `default` uses the table's primary key, sorted by item IDs, instead of an index |

Unrecognized parameters are ignored.

## Root

`get_root` reads `s3://<CIRRUS_DATA_BUCKET>/catalog.json`, which Cirrus does not create, and returns:

- `id`: the catalog's `id` with `-state-api` appended.
- `description`: the catalog's `description` followed by a space and `State API`.
- `links`: a `self` link to the API root, one `child` link per entry under the catalog's `cirrus.workflows` object, titled `<collections> - <workflow>` and pointing at `/<collections>/workflow-<workflow>`, and a `stac` link to the `catalog.json` object.

The root URL is built from the request's `domainName` and `path`. If API Gateway supplies no `domainName`, `root_url` is `None` and `get_root` raises a `TypeError` from `urljoin`.

```json title="Example response, illustrative values"
{
  "id": "my-deployment-state-api",
  "description": "My Deployment State API",
  "links": [
    {"title": "home", "rel": "self", "type": "application/json", "href": "https://<api-id>.execute-api.<region>.amazonaws.com/dev/"},
    {"title": "sentinel2 - publish", "rel": "child", "type": "application/json", "href": "https://<api-id>.execute-api.<region>.amazonaws.com/dev/sentinel2/workflow-publish"},
    {"title": "STAC", "rel": "stac", "type": "application/json", "href": "s3://my-data-bucket/catalog.json"}
  ]
}
```

## `/stats`

`get_stats` returns counts grouped by state under `state_transitions`:

- `daily`: one entry per day over the last 60 days.
- `hourly`: one entry per hour over the last 36 hours.
- `hourly_rolling`: the current partial hour and the previous hour, queried separately and concatenated.

Each entry has the shape `{"period": <str>, "interval": "day" | "hour", "states": [{"state": <str>, "unique_count": <int>, "count": <int>}, ...]}`.

The source is CloudWatch metrics when `CIRRUS_WORKFLOW_METRIC_NAMESPACE` is set, which a default main-stack deployment does. Counts come from `WorkflowMetricReader`, reshaped by `filter_for_dashboard`: the `CLAIMED_PROCESSING` and `STARTED_PROCESSING` event types are reported as `CLAIMED` and `PROCESSING`, and event types that are not state names, such as `ALREADY_PROCESSING`, are dropped. On this path `unique_count` equals `count`. When the namespace is unset, the function falls back to the deprecated Timestream event database, and when neither is configured it returns:

```json title="/stats with no metrics source"
{
  "error": "Endpoint /stats is not enabled because timeseries database is not configured"
}
```

with status 404. See [Workflow events](workflow-events.md#destinations).

## Summary

`/<collections>/workflow-<workflow>` splits the partition key on its last underscore and returns one count per state:

```json title="Example response, illustrative values"
{
  "collections": "sentinel2",
  "workflow": "publish",
  "counts": {
    "PROCESSING": 0,
    "SUCCEEDED": 1024,
    "FAILED": 3,
    "INVALID": 1,
    "ABORTED": 0,
    "CLAIMED": 0
  }
}
```

Each count comes from `StateDB.get_counts` over the `state_updated` index, honoring `since` and `limit`. The sort parameters do not apply.

## Items page

`/<collections>/workflow-<workflow>/items` returns `{"items": [...], "nextkey": "<payload_id>"}`. The page comes from `StateDB.get_items_page`, filtered by `state` and `since` and paged by `limit`, `nextkey`, `sort_ascending`, and `sort_index`. Each record is converted by `StateDB.dbitem_to_item` and then `to_current`, so it has the fields listed under [State database: Fields](state-database.md#fields) plus the legacy `catid` and `catalog` aliases.

When more records remain, the response also carries `nextkey`, the `payload_id` to pass as the `nextkey` query parameter of the next request. Its absence means the last page.

## Single record

`/<collections>/workflow-<workflow>/<itemids>` returns the record for that payload ID in the same shape as one entry of the items page.

## Errors

| Condition | Result |
| --- | --- |
| Path is not empty, not `stats`, and lacks `/workflow-` | 400 with the plain string `"<path> not found"`, where `<path>` is the request context path |
| `/stats` with no metrics source configured | 404 with the JSON error above |
| Payload ID not found on the single-record route | Unhandled `PayloadNotFoundError`. A Lambda invocation error, not a JSON response |
| Malformed `since` | Unhandled `ValueError` |
| Non-integer `limit` | Unhandled `ValueError` |

Any path containing `/workflow-` is assumed to parse into a valid key. There is no 404 for a well-formed but unknown collections-workflow; the summary route returns zero counts.

## Data sources and permissions

| Source | Used for | Configuration |
| --- | --- | --- |
| State table | Summary, page, and single-record routes | `CIRRUS_STATE_DB`. The role grants `dynamodb:Query`, `Scan`, `GetItem`, and `DescribeTable` on the table and its indexes |
| Data bucket | Root route | `CIRRUS_DATA_BUCKET`. The role grants `s3:ListBucket`, `GetObject`, and `GetBucketLocation` |
| [Payload bucket](payload-bucket.md) | The `input_payload_url` and `output_payload_url` fields on records | `CIRRUS_PAYLOAD_BUCKET` and `CIRRUS_PAYLOAD_ROOT_PREFIX`. The URLs are constructed, not read, so no S3 permission on this bucket is needed |
| CloudWatch metrics | `/stats` | `CIRRUS_WORKFLOW_METRIC_NAMESPACE`. `cloudwatch:GetMetricData`, `GetMetricStatistics`, and `ListMetrics` are granted only when the namespace is non-empty |
| Timestream | `/stats` fallback, deprecated | `CIRRUS_EVENT_DB_AND_TABLE`. Not set by any template |

The function runs with a 15-second timeout and 256 MB of memory. It reads state and never writes it.
