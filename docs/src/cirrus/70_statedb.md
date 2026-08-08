# State Database

The state database (StateDB) is a DynamoDB table that tracks the state of every
payload a Cirrus deployment has processed. It is a core piece of the
[Cirrus architecture](20_arch.md), created by the CloudFormation core stack,
that prevents duplicate workflow executions, records processing errors, and
lets [monitoring](80_monitoring.md) and CLI tooling query execution history.

DynamoDB is a managed, non-relational (NoSQL) key-value store: items are
independent of each other, addressed by a key, with no enforced schema beyond
the key attributes. Cirrus relies on this for cheap, high-throughput
read/write of one item per payload execution, with no cross-item joins
needed.

The StateDB is used at several points in the Cirrus pipeline:

- **[`process`](../components/functions/index.md#process) function** — checks
  existing state before starting a workflow execution (to skip duplicates or
  already-succeeded payloads), claims the payload for processing, and
  transitions it to `PROCESSING`.
- **[`update-state`](../components/functions/index.md#update-state) function** —
  records the terminal state (`SUCCEEDED`, `FAILED`, `INVALID`, or `ABORTED`)
  after a Step Functions execution finishes.
- **[`api`](../components/functions/index.md#api) function** — queries the StateDB
  for aggregate execution counts and individual item records.
- **The Cirrus CLI (`cirrus manage`)** — queries the StateDB directly for
  execution status, and to retrieve input/output payloads.

## Key schema

The table's partition (hash) key is `collections_workflow` and its sort
(range) key is `itemids`, defined on the `StateTable` resource in
`cloudformation/core/base.yaml`. Two Global Secondary Indexes (GSIs) share the
same partition key but sort on a different attribute:

| Index | Partition key | Sort key |
| --- | --- | --- |
| Primary (table) | `collections_workflow` | `itemids` |
| `state_updated` GSI | `collections_workflow` | `state_updated` |
| `updated` GSI | `collections_workflow` | `updated` |

`collections_workflow` and `itemids` are derived from a payload's
`payload_id`, which has the form
`<collections>/workflow-<workflow>/<itemids>`. `StateDB.payload_id_to_key`
splits the payload ID on `/workflow-` and joins the collections and workflow
name with an underscore to form `collections_workflow`.
Because the join uses `_`, workflow names must not contain underscores;
`split_collections_workflow` reverses this by splitting on the *last*
underscore, since the collections portion may itself contain underscores.

`StateDB.query` always keys on `collections_workflow` and selects an index
based on the query: filtering by `state` uses the `state_updated` GSI
(`begins_with` or `between` on `state_updated`); filtering by `since` alone
uses the `updated` GSI; unfiltered queries use the primary key, sorted by
`itemids`.

## Fields

Field names below match the raw DynamoDB item (the "dbitem"). `StateDB.get_item`
/ `get_items` convert this to a friendlier shape via `dbitem_to_item`;
differences are noted in the table.

| Field | Type | Written by | Notes |
| --- | --- | --- | --- |
| `collections_workflow` | string | all state-change methods | Partition key. `<collections>_<workflow>`. |
| `itemids` | string | all state-change methods | Sort key. The item-ID portion of the payload ID. Note the lowercase `ids` — not `itemIDs`. |
| `state_updated` | string | all state-change methods | `<STATE>_<isotimestamp>`, e.g. `PROCESSING_2024-01-01T00:00:00+00:00`. Sort key of the `state_updated` GSI; current state is parsed from the prefix. |
| `updated` | string | all state-change methods | ISO UTC timestamp of the most recent update. Sort key of the `updated` GSI. |
| `created` | string | first state-change call for a payload | ISO UTC timestamp; set once via `if_not_exists`, never overwritten. |
| `executions` | list[string] | `claim_processing` | Step Functions execution ARNs, appended (not replaced) on each claim — a payload run multiple times accumulates entries here. Converted to console URLs in `dbitem_to_item`. |
| `claimed_at` | string | `claim_processing` | ISO UTC timestamp of the most recent claim. Only present after a payload has been claimed at least once. |
| `outputs` | list[string] | `set_outputs`, `set_succeeded` | URLs of output STAC items. Removed by `claim_processing` on a new claim. |
| `last_error` | string | `set_failed`, `set_invalid` | Error message. Removed by `claim_processing` on a new claim. |

`dbitem_to_item` (used by `get_item`/`get_items`, not present on the raw
table) adds:

| Field | Type | Notes |
| --- | --- | --- |
| `payload_id` | string | Reconstructed from the key via `key_to_payload_id`. |
| `collections` | string | Split out of `collections_workflow`. |
| `workflow` | string | Split out of `collections_workflow`. |
| `items` | string | Copied from the dbitem's `itemids` — note the renamed key. |
| `state` | string | Parsed from the `state_updated` prefix. |
| `input_payload_url` | string \| null | S3 URL of the input payload for the most recent execution, from `PayloadBucket.get_input_payload_url`. `null` if there is no execution yet. |
| `output_payload_url` | string \| null | S3 URL of the output payload, populated only when `state == SUCCEEDED`; otherwise `null`. |

!!! note "Legacy `catalog`/`catid` aliasing"
    `cirrus.lib.statedb.to_current` maps a converted item's `payload_id` to
    `catid` and `input_payload_url` to `catalog`. This exists solely for
    compatibility with cirrus-dashboard and is not part of the StateDB schema
    itself — new integrations should use `payload_id` and
    `input_payload_url` directly.

## States

States are defined in `StateEnum` in `src/cirrus/lib/enums.py`:

| State | Meaning |
| --- | --- |
| `CLAIMED` | A Step Functions execution has been reserved for this payload but has not yet started running. |
| `PROCESSING` | The claimed execution has started running. |
| `SUCCEEDED` | The workflow execution completed successfully. |
| `FAILED` | The workflow execution failed. |
| `INVALID` | The workflow execution failed because a task raised an invalid-input error — the payload will not succeed without modification. |
| `ABORTED` | The workflow execution was aborted. |

`CLAIMED` exists to close a race between duplicate Step Functions executions
for the same payload. `StateDB.claim_processing` sets the state to `CLAIMED`,
records `claimed_at`, and appends the prospective execution ARN to
`executions`, under a condition expression that fails if the item is already
`PROCESSING` or `CLAIMED`. This lets a
caller reserve a payload before starting its Step Functions execution, so a
second, concurrent attempt to process the same payload is rejected at the
DynamoDB layer rather than resulting in two executions. Once the reserved
execution actually starts, `StateDB.set_processing` transitions the item from
`CLAIMED` to `PROCESSING`, again gated by a condition expression requiring the
current state to be `CLAIMED`.

The other terminal-state setters (`set_succeeded`, `set_failed`,
`set_invalid`, `set_aborted`) are called by the
[`update-state`](../components/functions/index.md#update-state) function once a
Step Functions execution finishes.

## Querying via the Cirrus CLI

The `cirrus manage` command group queries the StateDB directly
(`src/cirrus/management/commands/manage.py`):

- `get-state <payload-id>` — fetch the StateDB record for a single payload.
- `query` — filter records by `collections_workflow`, `state`, `since`, and
  error-message prefix, returned as newline-delimited JSON.
- `get-input-payloads` — same filtering as `query`, but resolves each match
  to its input payload in the payload bucket and streams the payloads
  themselves.

See the [CLI reference](../cli/04_commands.md) for the full command list and options.

## Deleting StateDB items

Deleting records is not part of normal operation. If needed,
`StateDB.delete_item(payload_id)` removes a single record by its payload ID.
