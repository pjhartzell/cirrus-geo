# Upgrading to 2.0

Cirrus 2.0.0 reorganizes the payload bucket, renames the `COMPLETED` state to `SUCCEEDED`, renames two CLI commands, and changes several library APIs. This page covers what an existing deployment has to do. The [changelog](../about/changelog.md) lists every change.

## Operators

### Payload bucket layout

Payload keys now live under a root prefix, `CIRRUS_PAYLOAD_ROOT_PREFIX`, default `cirrus`. Each execution's input and output are stored at `<root>/executions/<payload_id>/<execution_id>/input.json` and `output.json`, and transient objects, meaning oversized payloads, Batch job input and output, and rejected messages, are under `<root>/tmp/`. See [Payload bucket](../reference/payload-bucket.md).

The templates gained a `PayloadRootPrefix` parameter, and the payload bucket a lifecycle rule expiring `<root>/tmp/` after 10 days. A deployment with its own bucket needs an equivalent rule.

### `COMPLETED` is now `SUCCEEDED`

The state database, the HTTP API, and workflow events use `SUCCEEDED`. The event type `ALREADY_COMPLETED` is now `ALREADY_SUCCEEDED`. Any query, alarm, or dashboard matching the string `COMPLETED` needs updating.

### Event field changes

- `payload_url` is now `input_payload_url`.
- `SUCCEEDED` and `ALREADY_SUCCEEDED` events carry a new `output_payload_url`.
- `CLAIMED_PROCESSING` events, and `FAILED` events emitted before an upload happened, carry no payload URL, since none exists yet.

See [Workflow events](../reference/workflow-events.md#event-fields).

### Running the migration

The `migrate` command brings an existing state database and payload bucket into the 2.0 layout:

```console
cirrus manage <deployment> migrate --dry-run
cirrus manage <deployment> migrate
```

It scans the whole table on every run and processes each record that has no `claimed_at` field, treating one that does as already migrated. For each such record, in order:

1. Copies the input payload from the 1.x key `<payload_id>/input.json` to the new execution key, when the record has an execution. A payload that was never stored at the old key, for example one submitted as a URL reference, is skipped.
2. For a record in the legacy `COMPLETED` state updated within `--since-days` days, default 90, fetches the output from the Step Functions execution and writes it to the new output key. Executions older than Step Functions' retention are skipped.
3. Updates the record: `COMPLETED` becomes `SUCCEEDED`, `claimed_at` is set from `created`, `last_error` is removed unless the state is `FAILED`, and `outputs` is removed unless the state is `SUCCEEDED` or `COMPLETED`.

Step 3 runs last so that a failure partway through leaves the record unmarked and a rerun finishes it. `--dry-run` prints each planned copy and update to stderr without writing. S3 objects are copied, never moved, so the 1.x keys remain until the operator deletes them.

Run `migrate` once after deploying 2.0.0. Until it has run, `get-input-payload` and `get-output-payload` cannot find payloads for pre-2.0 executions.

## CLI users

| 1.x command | 2.0 command |
| --- | --- |
| `get-payload` | `get-input-payload` |
| `get-payloads` | `get-input-payloads` |

New commands: `get-output-payload`, `query`, `migrate`, and the top-level `cirrus version`. Management commands no longer accept user variables; that support was removed in 1.0.0 and only the help text had kept advertising it.

## Library consumers

Code importing `cirrus.lib` or `cirrus.management` should review these changes.

**`cirrus.lib.statedb`.** `StateDB.get_dbitem` raises `PayloadNotFoundError` instead of returning `None`. `set_completed` is now `set_succeeded`. `dbitem_to_item` is an instance method, not a classmethod. `payload_id_to_url`, `payload_key_to_url`, and `payload_id_to_bucket_key` are removed in favor of `payload_id_to_input_payload_url` and `payload_id_to_output_payload_url`. The module-level `get_payload_bucket` and `get_state_db` are removed. The converted record's `catalog` field is now `input_payload_url`, and `output_payload_url` and `claimed_at` are new. See [State database: Fields](../reference/state-database.md#fields).

**Payload bucket access.** `PayloadBucket` in `cirrus.lib.payload_bucket` is the one entry point for S3 payload keys. `PayloadManager.upload_to_s3` is removed.

**Exceptions.** `PayloadNotFoundError` moved from `cirrus.management.exceptions` to `cirrus.exceptions`. `NoExecutionsError` is removed, replaced by `ExecutionNotFoundError` in `cirrus.exceptions`. `NoPayloadUrlError` is new in `cirrus.management.exceptions` and `UndefinedPayloadBucketError` in `cirrus.lib.errors`. See [Errors and exceptions](../api/errors.md).

**`cirrus.management.deployment.Deployment`.** `yield_payloads` is replaced by `yield_workflow_items`, which yields state records, and `yield_input_payloads`, which resolves them to payloads and takes the `rerun` flag. `get_execution_arn` takes only a positional `payload_id`. `fetch_payload` takes a `direction` of `"input"` or `"output"` instead of `rerun`. `enqueue_payload` accepts a `dict`, `str`, `bytes`, or binary file object.
