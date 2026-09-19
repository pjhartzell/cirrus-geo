# Payload schema

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

`CirrusPayload` is a `cirrus.lib.cirrus_payload.CirrusPayload`, a subclass of
stac-task's `stactask.payload.Payload` (itself a `dict`). Its `validate()`
method runs stac-task's own validation first, then Cirrus-specific checks:

- **stac-task** (`Payload.validate`): resolves `process_definition`,
  `workflow_options`, `task_options_dict`, `upload_options`,
  `collection_mapping`, `items_as_dicts`, `collection_matchers`, and
  `collection_options` — raising `TypeError` if any of these are malformed —
  and rejects a payload that sets both `collection_matchers` and the legacy
  `upload_options.collections` (they're mutually exclusive).
- **Cirrus** (`CirrusPayload.validate`): `process` must be an array with at
  least one entry, the first entry must contain a `workflow` field, and `id`
  must match the [ID format](#id-format).

!!! note
    A `process` array with more than one entry, or with an entry that is
    itself an array, describes a chain of workflow executions rather than
    parameters for a single execution. See [Workflow
    chaining](../building-pipelines/chaining-workflows.md).

Validation beyond the payload's own structure — whether the input items
themselves are usable — is left to individual workflow tasks. A task that
receives input it can't process should raise an `InvalidInput` exception
(`stactask.exceptions.InvalidInput`), which the
[`update-state`](lambda-functions.md#update-state) function maps to the
`INVALID` state in the state database.

## ID format

A payload's `id` field tracks the individual execution of a workflow and must
match the pattern `<collections>/workflow-<workflow>/<itemids>`
(`cirrus.lib.utils.PAYLOAD_ID_REGEX`, `(?P<collections>.+)/workflow-(?P<workflow>[^/]+)/(?P<itemids>.+)`),
where `workflow` is the workflow name from the process definition. If a
submitted payload has no `id`, the [Cirrus CLI](../cli/using-the-cli.md) and
the [`process`](lambda-functions.md#process) function can generate one
(`CirrusPayload.set_id`):

- `collections` is taken from the process definition's `collections` field if
  present, otherwise it is derived from the sorted, `/`-joined set of
  `collection` values across the input `features` (or `none` if no item
  declares a collection).
- `itemids` is the sorted, `/`-joined set of item `id` values from `features`.

!!! warning "Workflow names must not contain underscores"
    The state database's partition key joins `collections` and `workflow`
    with an underscore (`StateDB.join_collections_workflow`), and reverses
    the join by splitting on the *last* underscore
    (`StateDB.split_collections_workflow`) — the `collections` segment may
    itself contain underscores, but `workflow` may not, or the split
    misparses the key. A workflow name containing an underscore produces a
    payload `id` that state-database lookups and updates for that execution
    will resolve incorrectly. See [State Database: Key
    schema](state-database.md#key-schema).

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
may perform additional validation beyond what `CirrusPayload.validate`
checks — see [Validation](#payload-schema) above.

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
| workflow          | string                               | **REQUIRED** Name of the workflow to run. Must not contain underscores — see [ID format](#id-format).                                            |
| collections       | string                               | Overrides the derived `collections` segment of a generated payload `id`                                                                           |
| replace           | bool                                 | If true, allows a rerun of the workflow that would otherwise be skipped based on the payload's current state (see [below](#the-replace-field-and-reruns)) |
| upload_options    | [Upload Options](#upload-options)    | Parameters controlling how task-uploaded assets are stored and published                                                                          |
| workflow_options  | Map\<str, object\>                   | Parameters merged into every task's `parameters` for this workflow execution                                                                      |
| tasks             | Map\<string, Map\<str, object\>\>    | A dictionary of task names (keys), each containing a dictionary of parameters for that task                                                       |
| chain_filter      | string                               | JSONPath filter applied to the previous workflow's output features (chaining only). See [Workflow chaining](../building-pipelines/chaining-workflows.md). |

### The replace field and reruns

This is the canonical description of when a (re)submitted payload actually
starts a workflow execution versus getting skipped, and how `replace`
changes that. It is enforced in two places:

1. **`PayloadManagers.process`** (`cirrus.lib.payload_manager`), called by
   the [`process`](lambda-functions.md#process) function, looks up the
   payload's current state in the state database and computes
   `_replace = replace or process_definition.get("replace", False)`
   (the `process()` method itself also takes a `replace` argument, used by
   the [migration tooling](#replace-in-migrations) below). It then decides
   per payload:

    ```python
    elif (
        state in (StateEnum.FAILED, StateEnum.ABORTED, StateEnum.CLAIMED, None)
        or _replace
    ):
        # attempt to claim and start the workflow
    else:
        # skip: wfem.skipping(...)
    ```

2. **`StateDB.claim_processing`**, called during that attempt, enforces a
   DynamoDB condition expression that fails if the record's current state
   begins with `PROCESSING` or `CLAIMED`. This closes the race between two
   concurrent attempts to process the same payload — it cannot be bypassed
   by `replace`.

Combining the two, for each state a payload record can be in:

| Current state  | Default (no `replace`) | With `replace: true`                                                                                     |
| -------------- | ----------------------- | ---------------------------------------------------------------------------------------------------------- |
| *(no record)*  | Runs                    | Runs                                                                                                        |
| `CLAIMED`      | Runs                    | Runs — resolves against the pending execution ARN already in the record rather than starting a new one     |
| `PROCESSING`   | Skipped                 | Skipped — blocked by the DynamoDB condition regardless of `replace`                                         |
| `SUCCEEDED`    | Skipped                 | Runs                                                                                                        |
| `FAILED`       | Runs                    | Runs                                                                                                        |
| `INVALID`      | Skipped                 | Runs                                                                                                        |
| `ABORTED`      | Runs                    | Runs                                                                                                        |

In short: without `replace`, a resubmission runs only if the payload has no
state database record yet, or its current state is `FAILED`, `ABORTED`, or
`CLAIMED`; `SUCCEEDED` and `INVALID` are skipped. Setting `"replace": true`
in the process definition also allows reruns from `SUCCEEDED` and `INVALID`.
A payload currently `PROCESSING` is always skipped — `replace` cannot
override an execution already underway.

A skipped payload is announced via a `WorkflowEventManager.skipping` event
(`ALREADY_PROCESSING`, `ALREADY_CLAIMED`, `ALREADY_SUCCEEDED`, or
`ALREADY_INVALID` — see [Monitoring](../operating/monitoring.md)). Each claim
appends a new Step Functions execution ARN to the state database's
`executions` list rather than replacing it, so a payload rerun with
`replace: true` accumulates multiple entries — see [State Database:
Fields](state-database.md#fields).

#### replace in migrations

`Deployment.yield_workflow_items` (`cirrus.management.deployment`) accepts a
`rerun` argument; when true, it sets `payload["process"][0]["replace"] = True`
on each yielded payload before returning it, giving migration and
backfill tooling the same rerun semantics described above without callers
setting the field by hand.

### tasks

The `tasks` field is a dictionary with an optional key for each task in the
workflow. If present, the value is a dictionary of parameters for that task.
A task reads its parameters as the combination of the workflow's
`workflow_options` and its own entry under `tasks`, with `tasks` values
taking precedence on key conflicts. The documentation for each task supplies
its list of available parameters.

## Upload Options

`upload_options` in the process definition controls how a task uploads and
publishes an item's data assets. See stac-task's `upload_item_assets_to_s3`
function (`stactask.asset_io`).

| Field Name      | Type               | Description                                                                                      |
| --------------- | ------------------ | ------------------------------------------------------------------------------------------------ |
| path_template   | string             | A string template for the location of uploaded assets. Defaults to `${collection}/${id}`.        |
| public_assets   | \[str\] or `"ALL"` | Asset keys that should be marked public when uploaded, or `"ALL"` for every asset in the item    |
| headers         | Map\<str, str\>    | Key/value headers to send when uploading assets to S3                                            |
| s3_urls         | bool               | If true, return `s3://<bucket>/<key>` URLs for uploaded assets instead of HTTPS URLs             |

### path_template

`path_template` controls the output location of an item's uploaded assets
using metadata from the item itself, via pystac's `LayoutTemplate`. The
template can contain fixed strings along with variables substituted from the
item. Variables resolve, in order, against the item's own attributes, then
its `properties`, then its `extra_fields`. A few variables carry special
meaning for STAC Items:

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
    items. stac-task deprecates this in favor of `collection_matchers`;
    `CirrusPayload.validate` rejects a payload that sets both.
