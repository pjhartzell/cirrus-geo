# State database

The state database is a DynamoDB table with one record per payload ID. It is what stops the same payload from running twice, records how each execution ended, and lets the CLI and HTTP API answer what happened to a payload. `cloudformation/core/base.yaml` creates it as `${ResourcePrefix}-state` with on-demand billing. All access goes through `StateDB` in `cirrus.lib.statedb`, which reads the table name from `CIRRUS_STATE_DB` and also needs `CIRRUS_PAYLOAD_BUCKET`, because it builds payload URLs from records.

Who writes and reads it:

- [`process`](lambda-functions.md#process) reads the current state of each incoming payload, claims it, and moves it to `PROCESSING`.
- [`update-state`](lambda-functions.md#update-state) writes the terminal state and error.
- [`api`](lambda-functions.md#api) reads records and counts.
- The Cirrus CLI reads records and resolves payload IDs to executions and stored payloads.

## Key schema

| Index | Partition key | Sort key |
| --- | --- | --- |
| Table | `collections_workflow` | `itemids` |
| `state_updated` GSI | `collections_workflow` | `state_updated` |
| `updated` GSI | `collections_workflow` | `updated` |

Both indexes project all attributes. The key is derived from the payload ID `<collections>/workflow-<workflow>/<itemids>`: `StateDB.payload_id_to_key` splits on `/workflow-`, then splits the remainder on its first `/`, and joins collections and workflow with an underscore. The reverse split, `split_collections_workflow`, cuts on the last underscore, which is why a workflow name may not contain one while a collections segment may. See [ID format](payload-schema.md#id-format).

`StateDB.query` always conditions on `collections_workflow` and picks the index from the filters: a `state` filter uses the `state_updated` index with a `begins_with` on the state name, or a `between` on `<state>_<start>` and `<state>_<now>` when `since` is also given; `since` alone uses the `updated` index; neither uses the table, sorted by `itemids`. An `error_begins_with` filter is applied as a DynamoDB filter expression on `last_error` after the key condition.

## Fields

The raw record, as `get-state` returns it:

| Field | Type | Written by | Notes |
| --- | --- | --- | --- |
| `collections_workflow` | string | every state change | Partition key, `<collections>_<workflow>` |
| `itemids` | string | every state change | Sort key, the item-ID segment of the payload ID |
| `state_updated` | string | every state change | `<STATE>_<isotimestamp>`, for example `PROCESSING_2026-01-01T00:00:00+00:00`. The current state is the prefix |
| `updated` | string | every state change | ISO timestamp of the latest change |
| `created` | string | first change only | Set with `if_not_exists`, never overwritten |
| `executions` | list of strings | `claim_processing` | Execution ARNs, appended on each claim, so a rerun payload accumulates entries |
| `claimed_at` | string | `claim_processing` | Timestamp of the latest claim |
| `last_error` | string | `set_failed`, `set_invalid` | `<error type>: <message>`. Removed by the next claim |
| `outputs` | list of strings | `set_outputs`, `set_succeeded` | Not written by any framework code path in this version; `update-state` calls `set_succeeded` without it. The methods remain for library callers. Removed by the next claim |

`StateDB.dbitem_to_item`, used by `get_item`, `get_items`, the `query` and `get-input-payloads` commands, and the HTTP API, returns a converted record instead:

| Field | Notes |
| --- | --- |
| `payload_id` | Rebuilt from the key |
| `collections`, `workflow` | Split out of `collections_workflow` |
| `items` | The `itemids` value under a different name |
| `state` | The prefix of `state_updated` |
| `created`, `updated` | Copied |
| `input_payload_url` | S3 URL of the most recent execution's input payload, or `null` if there is no execution yet |
| `output_payload_url` | S3 URL of the output payload, or `null` unless `state` is `SUCCEEDED` |
| `executions` | Each ARN converted to a Step Functions console URL. Present only when the record has executions |
| `outputs`, `last_error`, `claimed_at` | Copied when present |

`to_current` adds `catid` and `catalog` as aliases of `payload_id` and `input_payload_url`. They exist for cirrus-dashboard and are not part of the schema; new code should read the unaliased fields.

## States

`StateEnum` in `src/cirrus/lib/enums.py`:

| State | Meaning |
| --- | --- |
| `CLAIMED` | An execution is reserved for the payload and its ARN recorded, but the execution has not been confirmed as started |
| `PROCESSING` | The execution is running |
| `SUCCEEDED` | The execution succeeded |
| `FAILED` | The execution failed or timed out, or `process` could not start it |
| `INVALID` | A task raised `InvalidInput`. The payload will not succeed without modification and is skipped on resubmission unless `replace` is set |
| `ABORTED` | The execution was stopped |

`CLAIMED` exists to close a race. `claim_processing` sets it under a condition expression that fails if the record is already `CLAIMED` or `PROCESSING`, so two invocations of `process` holding the same payload cannot both start an execution. `set_processing` then moves the record to `PROCESSING` under a condition that it is currently `CLAIMED`. Which states a resubmitted payload runs from is defined in [The replace field and reruns](payload-schema.md#the-replace-field-and-reruns).

## Reading and deleting records

The CLI's `get-state`, `query`, and `get-input-payloads` commands read the table; see [Common workflows](../cli/common-workflows.md#check-state-and-stored-payloads). The [HTTP API](http-api.md) serves the same records and per-state counts.

Deleting a record is not part of normal operation. `StateDB.delete_item(payload_id)` removes one by payload ID.
