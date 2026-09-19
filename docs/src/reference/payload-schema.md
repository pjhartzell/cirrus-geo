# Payload schema

A Cirrus Payload is the JSON object that moves through a pipeline: the input items and the instructions for processing them. One payload starts one execution of one workflow. The shape is a GeoJSON FeatureCollection with a `process` field added:

```json
{
    "type": "FeatureCollection",
    "id": "sentinel2/workflow-publish/S2A_1",
    "features": [
        { "<stac-item-1>": "..." },
        { "<stac-item-2>": "..." }
    ],
    "process": [
        { "<process-definition>": "..." }
    ]
}
```

| Field | Type | Description |
| --- | --- | --- |
| `id` | string | Identifies the execution. See [ID format](#id-format). `process` generates one when it is absent |
| `type` | string | Conventionally `FeatureCollection`. Not validated |
| `features` | array of [Item](#item) | The input items. Must be an array when present, and must be present when `id` is, since the ID is derived from it |
| `process` | array of [Process definition](#process-definition) | **Required**, with at least one entry. Entries after the first describe a [chain](../building-pipelines/chaining-workflows.md) |

`CirrusPayload` (`cirrus.lib.cirrus_payload`) subclasses stac-task's `Payload`, itself a `dict`. Its `validate` method runs stac-task's validation and then Cirrus's own:

- **stac-task** reads `process`, `features`, and the process definition's `workflow_options`, `tasks`, `upload_options`, `collection_matchers`, and `collection_options`, raising `TypeError` when any has the wrong type, and raises `ValueError` when both `collection_matchers` and the legacy `upload_options.collections` are set.
- **Cirrus** requires `process` to be a non-empty array, `process[0]` to have a `workflow`, and `id` to match the ID format.

Validation stops at structure. Whether the items are usable is for tasks to decide: a task that cannot process its input raises `stactask.exceptions.InvalidInput`, which [`update-state`](lambda-functions.md#status-to-state) records as `INVALID`.

## ID format

`id` must match `<collections>/workflow-<workflow>/<itemids>`, the regular expression `PAYLOAD_ID_REGEX` in `cirrus.lib.utils`: `(?P<collections>.+)/workflow-(?P<workflow>[^/]+)/(?P<itemids>.+)`. `<workflow>` must equal the process definition's `workflow` for the state database key to resolve.

When a payload has no `id`, `CirrusPayload.set_id` builds one. `process` does this on intake, and so does `cirrus payload get-id`:

- `<collections>` is the process definition's `collections` field if set, otherwise the sorted, `/`-joined set of `collection` values across `features`, or `none` when no item has one.
- `<itemids>` is the sorted, `/`-joined set of item `id` values.

Because the same items through the same workflow always produce the same ID, the ID is what makes processing idempotent. Two submissions differing only in process definition parameters are the same payload to Cirrus.

!!! warning "Workflow names must not contain underscores"
    The state database joins `<collections>` and `<workflow>` with an underscore for its partition key and splits on the last underscore to recover them. A collections segment may contain underscores; a workflow name may not, or lookups for that payload resolve the wrong key. See [State database: Key schema](state-database.md#key-schema).

## Item

An input item is a JSON object. Cirrus requires only that it have an `id`:

| Field | Type | Description |
| --- | --- | --- |
| `id` | string | **Required** |

Items are ordinarily STAC Items, which lets tasks work across data sources. A workflow whose job is to create STAC metadata can take partial items as input, for example a stub carrying only the URLs a task needs to build the real item:

```json
{
    "features": [
        {
            "id": "tiles-15-V-WG-2022-3-21-0",
            "assets": {
                "tileInfo": {
                    "href": "https://roda.sentinel-hub.com/sentinel-s2-l2a/tiles/15/V/WG/2022/3/21/0/tileInfo.json"
                },
                "productInfo": {
                    "href": "https://roda.sentinel-hub.com/sentinel-s2-l2a/tiles/15/V/WG/2022/3/21/0/productInfo.json"
                },
                "metadata": {
                    "href": "https://roda.sentinel-hub.com/sentinel-s2-l2a/tiles/15/V/WG/2022/3/21/0/metadata.xml"
                }
            }
        }
    ]
}
```

The output of a workflow should be complete STAC Items, since that is what the publish topic's subscribers expect. Cirrus does not check.

## Process definition

The first element of `process` is the definition for the current execution.

| Field | Type | Description |
| --- | --- | --- |
| `workflow` | string | **Required.** The workflow to run. No underscores |
| `collections` | string | Overrides the `<collections>` segment of a generated `id` |
| `replace` | boolean | Run even if the payload's current state would otherwise skip it. See [below](#the-replace-field-and-reruns) |
| `workflow_options` | object | Parameters passed to every task in the workflow |
| `tasks` | object | Per-task parameters, keyed by task name. See [tasks](#tasks) |
| `upload_options` | [Upload options](#upload-options) | How a task uploads and publishes item assets |
| `collection_options` | object | Per-collection overrides, keyed by collection name. A `{"<collection>": {"upload_options": {...}}}` entry replaces `upload_options` for items in that collection |
| `collection_matchers` | array | Rules assigning each output item's `collection`. See [Assigning output collections](#assigning-output-collections) |
| `chain_filter` | string | JSONPath filter on the previous execution's output items. Chaining only; see [Chaining workflows](../building-pipelines/chaining-workflows.md#filtering-output-items) |

### The replace field and reruns

Whether a submitted payload starts an execution or is skipped depends on its current state database record and on `replace`. The decision is made in two places:

1. **`PayloadManagers.process`** (`cirrus.lib.payload_manager`), called by the [`process`](lambda-functions.md#process) function, reads the record and computes `_replace = replace or process_definition.get("replace", False)`, where the first `replace` is a method argument the CLI's migration tooling can pass. A payload runs when its state is `FAILED`, `ABORTED`, `CLAIMED`, or absent, or when `_replace` is true. Otherwise it is skipped and an `ALREADY_*` [workflow event](workflow-events.md) is emitted.
2. **`StateDB.claim_processing`** then writes `CLAIMED` under a DynamoDB condition that fails when the record is already `CLAIMED` or `PROCESSING`. This closes the race between two concurrent submissions of the same payload, and `replace` cannot bypass it.

| Current state | Without `replace` | With `replace: true` |
| --- | --- | --- |
| no record | Runs | Runs |
| `CLAIMED` | Runs, against the execution already reserved in the record | Same |
| `PROCESSING` | Skipped | Skipped. The condition blocks it regardless of `replace` |
| `SUCCEEDED` | Skipped | Runs |
| `FAILED` | Runs | Runs |
| `INVALID` | Skipped | Runs |
| `ABORTED` | Runs | Runs |

Each run appends a new execution ARN to the record's `executions` list, so a rerun payload accumulates entries and the most recent one is the one commands resolve to. See [State database: Fields](state-database.md#fields).

`get-input-payloads --rerun` and `Deployment.yield_input_payloads(rerun=True)` set `replace: true` on `process[0]` of each payload they return, which is how bulk reruns get these semantics without editing payloads by hand.

### tasks

`tasks` maps task names to parameter objects. A task built on stac-task reads `Task.parameters`, which merges `workflow_options` with the entry under its own `name`, the task's entry winning on conflicts. Each task documents the parameters it reads.

## Upload options

`upload_options` controls how a stac-task task uploads item assets, through `Task.upload_item_assets_to_s3` and stac-task's `upload_item_assets_to_s3` in `stactask.asset_io`.

| Field | Type | Description |
| --- | --- | --- |
| `path_template` | string | Template for the S3 location of uploaded assets. Must resolve to an `s3://` URL; stac-task's default `${collection}/${id}` has no bucket and fails at upload |
| `public_assets` | array of strings, or `"ALL"` | Asset keys to upload with a public-read ACL, or every asset |
| `headers` | object | Extra arguments passed to the S3 upload, such as `CacheControl` |
| `s3_urls` | boolean | Return `s3://` URLs for uploaded assets instead of HTTPS URLs. Default false |

The uploader takes each asset whose `href` is an existing local file, uploads it to `<path_template>/<file name>` with `ContentType` set from the asset's `type`, and rewrites the `href`. Assets whose `href` is not a local path are left unchanged.

### path_template

The template is resolved by pystac's `LayoutTemplate` against the item. A `${name}` variable resolves, in order, against the item's own attributes, its `properties`, and its `extra_fields`, with these special names:

| Variable | Value |
| --- | --- |
| `date` | The date part of the item's `datetime`, or `start_datetime` when `datetime` is null |
| `year`, `month`, `day` | Parts of the same date |
| `collection` | The item's collection ID |
| any property | For example `${mgrs:utm_zone}` |

A template of `s3://my-data-bucket/${collection}/${year}/${id}` places an item's assets under its collection and year.

### Assigning output collections

`collection_matchers` assigns each output item's `collection` before the payload is returned. stac-task's `Task.handler` evaluates the matchers in order per item after `process` returns, and the first match wins:

```json
{
    "workflow": "my-workflow",
    "collection_matchers": [
        {
            "type": "jsonpath",
            "collection_name": "landsat-derived",
            "pattern": "$[?(@.id =~ 'LC08.*')]"
        },
        {
            "type": "catch_all",
            "collection_name": "other-products"
        }
    ]
}
```

A `jsonpath` matcher assigns `collection_name` to items matching its `pattern`, a JSONPath expression evaluated against the item. A `catch_all` matcher matches every item and belongs last. An item matching no matcher keeps its existing `collection`.

The older form, `upload_options.collections`, maps a collection name to a JSONPath expression. stac-task warns that it is deprecated and rejects a payload that sets both.
