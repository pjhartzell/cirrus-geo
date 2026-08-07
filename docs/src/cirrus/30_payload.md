# Cirrus Payload

A Cirrus Payload is a JSON object containing input metadata along with
parameters for processing that metadata and associated data. A Cirrus payload
is used to start a single execution of a workflow.

At a high level, the payload looks like a GeoJSON FeatureCollection with an
additional `process` field:

```json
{
    "type": "FeatureCollection",
    "features": [
        { "<stac-item-1>": "..." },
        { "<stac-item-2>": "..." }
    ],
    "process": [
        { "<process-definition>": "..." }
    ]
}
```

A workflow task may take one or more items as input, and could output one or
more items. One common use case is to take in a single input item and
generate a single output item.

| Field Name   | Type                                          | Description                                                                 |
| ------------ | --------------------------------------------- | --------------------------------------------------------------------------- |
| id           | string                                        | An identifier for this execution. See [ID format](#id-format) below.        |
| type         | string                                        | GeoJSON object type. Conventionally `FeatureCollection`, but not validated. |
| features     | [[Item](#item)]                               | An array of STAC-like input items                                           |
| process      | [[Process Definition](#process-definition)]   | **REQUIRED** An array of process definitions, at least one                  |

Cirrus validates the payload before starting a workflow (`CirrusPayload.validate`):
`process` must be an array with at least one entry, and the first entry must
contain a `workflow` field. `id` must match the [ID format](#id-format).

!!! note
    A `process` array with more than one entry, or with an entry that is
    itself an array, describes a chain of workflow executions rather than
    parameters for a single execution. See [Workflow
    chaining](../components/workflows/chaining.md).

## ID format

A payload's `id` field tracks the individual execution of a workflow and must
match `<collections>/workflow-<workflow>/<itemids>`, where `workflow` is the
workflow name from the process definition. If a submitted payload has no
`id`, the [`cirrus` CLI](../cli/00_intro.md) and the process Lambda function can
generate one:

- `collections` is taken from the process definition's `collections` field if
  present, otherwise it is derived from the sorted, `/`-joined set of
  `collection` values across the input `features` (or `none` if no item
  declares a collection).
- `itemids` is the sorted, `/`-joined set of item `id` values from `features`.

## Item

An input item to Cirrus is commonly one or more STAC Items, allowing workflow
tasks to be interoperable across different data sources. For example, an NDVI
task could create an NDVI asset and add it to the item regardless of whether
the source was a Landsat or Sentinel STAC Item.

Workflows are also sometimes responsible for creating proper STAC Items,
mapping metadata in other formats into STAC. As far as Cirrus itself is
concerned, the only field an item needs is `id`.

| Field Name   | Type     | Description                         |
| ------------ | -------- | ----------------------------------- |
| id           | string   | **REQUIRED** An ID for this item    |

Each workflow task has its own requirements for the items it processes, and
may perform additional validation. A task that receives a payload failing its
validation should raise an `InvalidInput` exception, which marks the
execution in the state database as `INVALID`.

In the following example, the input item is a partial STAC Item using STAC
fields but missing most required fields (e.g., `geometry`, `datetime`). It
provides URLs to Sentinel-2 metadata that will be converted to a full STAC
Item by one of the workflow tasks:

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

While partial STAC Items make sense as input to workflows that create STAC
metadata, the final output of a Cirrus workflow should always contain an
array of complete STAC Items.

## Process Definition

The first element of the `process` array is the definition consulted for the
current (or next, when chaining) workflow execution.

| Field Name        | Type                                 | Description                                                                                                                                       |
| ----------------- | ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| workflow          | string                               | **REQUIRED** Name of the workflow to run                                                                                                          |
| collections       | string                               | Overrides the derived `collections` segment of a generated payload `id`                                                                           |
| replace           | bool                                 | If true, reruns the workflow regardless of the payload's current state (see [below](#replace))                                                    |
| upload_options    | [Upload Options](#upload-options)    | Parameters controlling how task-uploaded assets are stored and published                                                                          |
| workflow_options  | Map\<str, object\>                   | Parameters merged into every task's `parameters` for this workflow execution                                                                      |
| tasks             | Map\<string, Map\<str, object\>\>    | A dictionary of task names (keys), each containing a dictionary of parameters for that task                                                       |
| chain_filter      | string                               | JSONPath filter applied to the previous workflow's output features (chaining only). See [Workflow chaining](../components/workflows/chaining.md). |

### replace

By default, `PayloadManagers.process` only (re)starts a workflow execution
for a payload `id` whose current state database entry is `FAILED`,
`ABORTED`, `CLAIMED`, or has no entry at all — an `id` already `PROCESSING`
or `SUCCEEDED` is skipped. Setting `"replace": true` in the process
definition bypasses that check for every state except `PROCESSING` — a
payload with an execution already underway is skipped regardless, enforced
by a condition on the state database claim.

### tasks

The `tasks` field is a dictionary with an optional key for each task in the
workflow. If present, the value is a dictionary of parameters for that task.
A task reads its parameters as the combination of the workflow's
`workflow_options` and its own entry under `tasks`, with `tasks` values
taking precedence on key conflicts. The documentation for each task supplies
its list of available parameters.

## Upload Options

`upload_options` in the process definition controls how a task uploads and
publishes an item's data assets. See the stac-task
`upload_item_assets_to_s3` function.

| Field Name      | Type               | Description                                                                                      |
| --------------- | ------------------ | ------------------------------------------------------------------------------------------------ |
| path_template   | string             | A string template for the location of uploaded assets. Defaults to `${collection}/${id}`.        |
| public_assets   | \[str\] or `"ALL"` | Asset keys that should be marked public when uploaded, or `"ALL"` for every asset in the item    |
| headers         | Map\<str, str\>    | Key/value headers to send when uploading assets to S3                                            |
| s3_urls         | bool               | If true, return `s3://<bucket>/<key>` URLs for uploaded assets instead of HTTPS URLs             |

### path_template

`path_template` controls the output location of an item's uploaded assets
using metadata from the item itself. The template can contain fixed strings
along with variables substituted from the item. Variables resolve, in order,
against the item's own attributes, then its `properties`, then its
`extra_fields`. A few variables carry special meaning for STAC Items:

| Template variable    | Description                                                                               |
| -------------------- | ----------------------------------------------------------------------------------------- |
| date                 | The date (ISO format) of the item's `datetime`, or `start_datetime` if `datetime` is null |
| year                 | The year of the same date                                                                 |
| month                | The month of the same date                                                                |
| day                  | The day of the same date                                                                  |
| collection           | The item's collection ID                                                                  |
| \<property\>         | Any other item attribute or STAC property (e.g., `id`, `mgrs:utm_zone`)                   |

For example, a `path_template` of `${collection}/${id}` uploads all assets to
a path based on the item's collection and ID, under the default Cirrus data
bucket. If a complete S3 URL is provided instead (e.g.,
`s3://my-bucket/data/${collection}/${id}`), assets upload to that bucket
instead.

### Assigning output collections

A process definition may include a top-level `collection_matchers` field to
assign each output item's `collection` before publishing. It is a list of
matchers evaluated in order per item; the first match wins:

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

A `jsonpath` matcher assigns `collection_name` to items matching its
`pattern` (a JSONPath expression evaluated against the item); a `catch_all`
matcher matches every item and belongs last. Items matching no matcher keep
their existing `collection`.

!!! note
    Older payloads may instead set `upload_options.collections` — a mapping
    of output collection name to a JSONPath expression matched against
    items. stac-task deprecates this in favor of `collection_matchers`; the
    two are mutually exclusive on a single payload.
