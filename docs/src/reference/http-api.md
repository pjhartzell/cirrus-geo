# Cirrus API Endpoints

The [`api`](lambda-functions.md#api) Lambda function serves a
read-only HTTP API over the [state database](state-database.md) and workflow
event metrics. It is fronted by an Amazon API Gateway REST API, provisioned
by `cloudformation/core/api.yaml` and wired into the deployment by the
`ApiStack` nested stack in `cloudformation/main.yaml`. There is no Lambda
function URL; API Gateway is the only entry point.

## URL structure

`cloudformation/core/api.yaml` creates a `AWS::ApiGateway::RestApi` with a
`GET` method on the root resource and a `{proxy+}` greedy resource with a
`GET` method, both integrated with the `api` Lambda via `AWS_PROXY`
integration. The API is deployed to a single stage named `dev`
(`ApiStage.StageName`), giving an invoke URL of the form:

```text
https://<api-id>.execute-api.<region>.amazonaws.com/dev/<path>
```

`<api-id>` and the full invoke URL are exposed as the `ApiGatewayUrl` and
`ApiGatewayId` outputs of both `core/api.yaml` and the top-level
`main.yaml` stack. Authorization is `NONE` on both methods — the API is
unauthenticated at the API Gateway layer.

Because the REST API only defines `GET` methods, any other HTTP verb is
rejected by API Gateway itself before the Lambda is invoked.

## Path handling

`lambda_handler` (`src/cirrus/lambda_functions/api.py:264`) builds the
routed path from the raw API Gateway proxy event: it splits `event["path"]`
on `/`, drops empty segments, and strips a leading segment if it matches
the deployment stage (`event["requestContext"]["stage"]`, i.e. `dev`). The
remaining segments are rejoined with `/` to form `payload_id`, which is
then matched against the routes below. Because the `dev` stage prefix is
stripped, the examples in this page use the path as it appears after the
stage — i.e. what you'd request at
`https://<api-id>.execute-api.<region>.amazonaws.com/dev/<path>`.

## Routes

All routes respond to `GET` only and return a JSON body. CORS is open on
every response: `response()` (`api.py:113`) adds
`Access-Control-Allow-Origin: *` and `Access-Control-Allow-Credentials: true`
to every reply, including errors.

| Path | Handler logic | Description |
| --- | --- | --- |
| `/` | `get_root` (`api.py:134`), called at `api.py:306` | Deployment root catalog with links to each collections/workflow summary. |
| `/stats` | `get_stats` (`api.py:210`), called at `api.py:308` | Aggregate workflow-event counts by state, daily/hourly/rolling-hour. |
| `/<collections>/workflow-<workflow>` | `summary` (`api.py:250`), called at `api.py:328` | Per-state record counts for a collections/workflow pair. |
| `/<collections>/workflow-<workflow>/items` | `StateDB.get_items_page`, called at `api.py:345` | Paginated list of state database records for a collections/workflow pair. |
| `/<collections>/workflow-<workflow>/<itemids>` | `StateDB.get_dbitem` / `dbitem_to_item`, called at `api.py:359` | Single state database record for one payload ID. |

Route dispatch (`api.py:304`-`360`) is a sequence of checks against
`payload_id`, not a router with named parameters:

1. Empty path → root.
2. `stats` → stats.
3. Any path without the literal substring `/workflow-` → 400 (see
   [Errors](#errors)).
4. Otherwise the path is parsed with `StateDB.payload_id_to_key`
   (`src/cirrus/lib/statedb.py:777`), which splits on `/workflow-` to get
   `collections_workflow`, then splits the remainder on the first `/` to
   get `itemids`. If `itemids` is empty, it's the collections/workflow
   summary route; if `itemids == "items"`, it's the paginated items route;
   any other value is treated as the item-ID portion of a specific
   `payload_id` and looked up directly.

Because `itemids == "items"` is a literal string match, a payload whose
item-ID portion is literally `items` is not reachable through the
single-item route — it resolves to the paginated `items` route instead.

## Query parameters

Parsed once in `lambda_handler` (`api.py:291`-`302`) and applied to the
summary and items routes:

| Parameter | Applies to | Default | Notes |
| --- | --- | --- | --- |
| `state` | summary, items | none (unfiltered) | One of `PROCESSING`, `SUCCEEDED`, `FAILED`, `INVALID`, `ABORTED`, `CLAIMED` (`StateEnum`). Selects the `state_updated` GSI in `StateDB.query`. |
| `since` | summary, items | none (unfiltered) | Look-back window relative to now, parsed by `parse_since` (`src/cirrus/lib/utils.py:31`): an integer immediately followed by `d`, `h`, or `m` — e.g. `since=10d`. No space between the number and the unit; `parse_since` raises `ValueError` on any other format. |
| `limit` | summary, items | `100000` | Cast with `int()`; a non-integer value raises an unhandled `ValueError` (500 from the Lambda runtime, not a JSON error response). For the summary route, counts above `limit` are reported as the string `"<limit>+"` instead of an exact number (`StateDB.get_counts`). |
| `nextkey` | items only | none | A `payload_id` returned as `nextkey` in a previous `items` response; used to fetch the next page via `StateDB.get_items_page`. |
| `sort_ascending` | items only | `0` (descending) | Parsed as `bool(int(...))`; pass `1` for ascending. |
| `sort_index` | items only | `updated` | Forwarded to `StateDB.query`; `"default"` uses the table's primary key (sorted by `itemids`) instead of a GSI. |

Unrecognized query parameters are read via `.get()` calls with defaults and
are otherwise ignored.

## Root (`/`)

`get_root` (`api.py:134`) reads `catalog.json` from the data bucket
(`s3://<CIRRUS_DATA_BUCKET>/catalog.json`) and returns a STAC-catalog-like
object:

- `id`: `"<catalog id>-state-api"`.
- `description`: `"<catalog description> State API"`.
- `links`: a `self` link to the API root, one `child` link per
  collections/workflow pair found under the catalog's `cirrus.workflows`
  object (title `"<collections> - <workflow>"`, href
  `<root_url>/<collections>/workflow-<workflow>`), and a `stac` link
  pointing at the `catalog.json` object itself.

`root_url` is derived from the incoming request
(`https://<domain><requestContext.path>/`); if API Gateway doesn't supply a
`domainName` in `requestContext` the function falls back to `root_url =
None`, and links are built with `urljoin(None, ...)`.

```json title="Example response — illustrative values"
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

`get_stats` (`api.py:210`) returns aggregate workflow-event counts grouped
by state, keyed under `state_transitions`:

- `daily`: 60-day window, one entry per day.
- `hourly`: 36-hour window, one entry per hour.
- `hourly_rolling`: the current partial hour plus the prior hour, queried
  separately and concatenated.

Each entry has the shape `{"period": <str>, "interval": <str>, "states":
[{"state": <str>, "unique_count": <int>, "count": <int>}, ...]}`. `period`
is a date or timestamp string; `interval` is the literal string `"day"` or
`"hour"`.

Data source, in order of preference:

1. If `WorkflowMetricReader.enabled()` is true (`CIRRUS_WORKFLOW_METRIC_NAMESPACE`
   is set to a non-empty namespace), counts come from CloudWatch metrics via
   `WorkflowMetricReader.aggregated_by_event_type` /
   `query_hour`, reshaped by `filter_for_dashboard` (`api.py:164`). That
   function renames the `CLAIMED_PROCESSING` and `STARTED_PROCESSING`
   workflow-event types to `CLAIMED` and `PROCESSING` respectively, and
   drops any event type that isn't a `StateEnum` value (i.e. non-terminal
   diagnostic events like `ALREADY_PROCESSING` or
   `DUPLICATE_ID_ENCOUNTERED` are excluded from `/stats`).
2. Otherwise, `EventDB` (Timestream) is queried directly via `daily`/`hourly`
   in `src/cirrus/lib/eventdb.py`, gated by the `CIRRUS_EVENT_DB_AND_TABLE`
   environment variable. This is a deprecated fallback path — see
   [Monitoring](../operating/monitoring.md#workflow-events).
3. If neither is configured, `EventDB._query` raises `EventsDisabledError`,
   which `get_stats` catches and returns `None` for.

The top-level `cloudformation/main.yaml` defaults `EnableWorkflowMetrics`
to `'true'`, deploying the metrics stack and passing its
`${ResourcePrefix}-workflow` namespace into the functions stack — so a
default main-stack deployment has the CloudWatch source enabled and
`/stats` returns data. `CIRRUS_EVENT_DB_AND_TABLE` is never set by the
in-repo templates. With `EnableWorkflowMetrics` set to `'false'` (or when
deploying `core/functions.yaml` standalone, where `WorkflowMetricNamespace`
defaults to `''`), both sources are disabled and `/stats` returns:

```json title="/stats — 404 when no metrics source is configured"
{
  "error": "Endpoint /stats is not enabled because timeseries database is not configured"
}
```

with HTTP status `404`. See [Monitoring](../operating/monitoring.md#workflow-events)
for the workflow-metrics machinery behind this endpoint.

## Collections/workflow summary (`/<collections>/workflow-<workflow>`)

`summary` (`api.py:250`) splits `collections_workflow` back into
`collections` and `workflow` (on the last underscore) and returns per-state
counts:

```json title="Example response — illustrative values"
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

`counts` has one key per `StateEnum` member. Each value is produced by
`StateDB.get_counts`, which queries the `state_updated` GSI for that state
(honoring `since`, `limit`, `sort_ascending`, `sort_index`) and returns
either an integer or, if the count exceeds `limit`, the string
`"<limit>+"`.

## Items page (`/<collections>/workflow-<workflow>/items`)

Returns a page of state database records:

```json title="Response shape"
{
  "items": [ { "...": "see fields below" } ]
}
```

`items` is built from `StateDB.get_items_page`, filtered by `state` and
`since` and paginated by `limit`/`nextkey`/`sort_ascending`/`sort_index`.
Each raw item is converted with `StateDB.dbitem_to_item`
(`src/cirrus/lib/statedb.py:708`) and then `to_current`
(`src/cirrus/lib/statedb.py:24`) before being added to the response — see
[state database fields](state-database.md#fields) for the full field list
(`payload_id`, `collections`, `workflow`, `items`, `state`, `created`,
`updated`, `input_payload_url`, `output_payload_url`, and conditionally
`executions`, `outputs`, `last_error`, `claimed_at`). `to_current` also adds
the legacy `catid`/`catalog` aliases documented on that page.

The response contains only the `items` array. `StateDB.get_items_page`
computes a `nextkey` continuation token from DynamoDB's
`LastEvaluatedKey`, but `lambda_handler` (`api.py:354`) rebuilds the
response body with only `items`, so the token is never returned to the
client. To paginate, pass the `payload_id` of the last item in the current
page as the `nextkey` query parameter of the next request — the
continuation key is derived from that record's attributes.

## Single item (`/<collections>/workflow-<workflow>/<itemids>`)

Returns one state database record — the same per-item shape as an entry in
the `items` array above — for the given `payload_id`
(`<collections>/workflow-<workflow>/<itemids>`). Built from
`StateDB.get_dbitem` → `dbitem_to_item` → `to_current`.

## Errors

| Condition | Status | Body |
| --- | --- | --- |
| Path doesn't contain `/workflow-` and isn't `""` or `stats` | 400 | `"<path> not found"` (plain string, not an object) — `<path>` is `event["requestContext"]["path"]`, which is `None` if API Gateway didn't populate `domainName`. |
| `/stats` requested with no metrics source configured | 404 | `{"error": "Endpoint /stats is not enabled because timeseries database is not configured"}` |
| `payload_id` not found in the state database (single-item route) | unhandled `PayloadNotFoundError` from `StateDB.get_dbitem` | Not caught in `lambda_handler` — surfaces as a Lambda invocation error, not a JSON error response. |
| Malformed `since` (e.g. missing unit suffix, space before the unit) | unhandled `ValueError` from `parse_since` | Not caught — Lambda invocation error. |
| Non-integer `limit` | unhandled `ValueError` from `int()` | Not caught — Lambda invocation error. |

There is no route-level 404 for well-formed but non-matching paths beyond
the `/workflow-` substring check above — any path containing `/workflow-`
is assumed to parse into a valid `collections_workflow`/`itemids` key.

## Access and data sources

| Source | Used for | Configuration |
| --- | --- | --- |
| State database (DynamoDB) | Summary, items, single-item routes | `CIRRUS_STATE_DB` env var, set from `StateTable` in `cloudformation/core/functions.yaml`. `ApiLambdaRole` grants `dynamodb:Query`, `Scan`, `GetItem`, `DescribeTable` on the table and its indexes. |
| Data bucket (S3) | Root route (`catalog.json`) | `CIRRUS_DATA_BUCKET` env var. `ApiLambdaRole` grants `s3:ListBucket`, `GetObject`, `GetBucketLocation` on `CirrusDataBucket*`. |
| [Payload bucket](payload-bucket.md) (S3) | `input_payload_url`/`output_payload_url` fields on item responses | `CIRRUS_PAYLOAD_BUCKET` / `CIRRUS_PAYLOAD_ROOT_PREFIX` env vars, read indirectly through `StateDB`'s `PayloadBucket` instance — these are constructed URLs, not objects the `api` function reads directly. |
| CloudWatch metrics | `/stats` (preferred source) | `CIRRUS_WORKFLOW_METRIC_NAMESPACE` env var; `ApiLambdaRole` conditionally grants `cloudwatch:GetMetricData`, `GetMetricStatistics`, `ListMetrics` when `WorkflowMetricNamespace` is non-empty. |
| Timestream (`EventDB`) | `/stats` (deprecated fallback) | `CIRRUS_EVENT_DB_AND_TABLE` env var (pipe-separated `database\|table`); not set by the reference CloudFormation. |

The `ApiLambda` resource (`cloudformation/core/functions.yaml`) runs with a
15-second timeout and 256 MB memory, and is not part of the payload
processing path — it only reads state, never writes it.
