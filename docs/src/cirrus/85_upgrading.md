# Upgrading to 2.0

Cirrus v2.0.0 reorganizes the payload bucket, renames the `COMPLETED` state
to `SUCCEEDED`, and changes several management CLI commands and library
APIs. This guide is organized by audience: operators running a deployment,
CLI users, and code that imports `cirrus.lib` or `cirrus.management`
directly.

!!! note
    Full details are in the [v2.0.0 changelog entry](../about/changelog.md).
    This guide covers the changes relevant to upgrading an existing
    deployment; it does not repeat every addition.

## Operators

### Payload bucket reorganization

All payload S3 keys now live under a configurable root prefix (default
`cirrus`, set via `CIRRUS_PAYLOAD_ROOT_PREFIX`). Input and output payloads
are stored per execution at:

```
{root_prefix}/executions/{payload_id}/{execution_id}/input.json
{root_prefix}/executions/{payload_id}/{execution_id}/output.json
```

Temporary objects (oversized payloads, batch task input, invalid payloads)
are stored under `{root_prefix}/tmp/`. See the
[Payload Bucket](75_payload_bucket.md) reference for the full key layout.

CloudFormation templates now include a `PayloadRootPrefix` parameter
(defaults to `cirrus`), and the payload bucket has a lifecycle rule that
expires objects under `{root_prefix}/tmp/` after 10 days. With the new
layout, a single lifecycle policy on `{root_prefix}/tmp/` is sufficient to
clean up all temporary objects.

### COMPLETED renamed to SUCCEEDED

The state database, EventDB, and API responses now use the state name
`SUCCEEDED` instead of `COMPLETED`. The workflow event type
`ALREADY_COMPLETED` is renamed to `ALREADY_SUCCEEDED`. Any queries, alerts,
or dashboards that match on the string `COMPLETED` need to be updated to
match `SUCCEEDED`.

### Event field renames

Workflow events changed shape:

- `payload_url` is renamed to `input_payload_url`.
- A new `output_payload_url` field is included on `SUCCEEDED` and
  `ALREADY_SUCCEEDED` events.
- `CLAIMED` events, and some `FAILED` events, no longer include a payload
  URL field at all — these are emitted before the payload is uploaded to
  S3, so no valid URL exists yet.

### Running the migration

The `migrate` management CLI command migrates state database records and
copies payloads into the new bucket organization for an existing
deployment:

```console
cirrus manage <deployment> migrate --dry-run
cirrus manage <deployment> migrate
```

For each record, `migrate`:

- Renames a legacy `COMPLETED` state to `SUCCEEDED` in `state_updated`.
- Sets a `claimed_at` timestamp from the record's `created` field, if not
  already present.
- Removes `last_error` from records that aren't in a `FAILED` state, and
  `outputs` from records that aren't `SUCCEEDED`.
- Copies the input payload from its legacy S3 key to the new
  `{root_prefix}/executions/{payload_id}/{execution_id}/input.json` key,
  if an execution and input payload exist. Payloads that were stored as
  URL references rather than uploaded to S3 are not copied.
- For records that were legacy `COMPLETED` and updated within the
  `--since-days` window, fetches the Step Functions execution output and
  uploads it to the new output payload key. Older executions fall outside
  the Step Functions history retention window and are skipped.

A record that already has a `claimed_at` field is treated as already
migrated and skipped.

`--dry-run` previews every DynamoDB update and S3 copy without writing
anything. `--since-days` sets the cutoff, in days, for fetching Step
Functions outputs for legacy `COMPLETED` records; it defaults to 90,
matching the Step Functions execution history retention limit.

The migration runs a full DynamoDB table scan every invocation. It is
idempotent — safe to re-run — but each run rescans the entire table.
S3 objects are only ever copied, never moved: cleaning up payloads outside
the new key layout is left to the operator.

!!! note
    Run `migrate` once after deploying the v2.0.0 release to bring an
    existing deployment's state database and payload bucket in line with
    the new organization.

## CLI users

Two management CLI commands were renamed:

| Old name       | New name             |
| -------------- | --------------------- |
| `get-payload`  | `get-input-payload`   |
| `get-payloads` | `get-input-payloads`  |

New commands added in this release:

- `get-output-payload` — fetch the output payload for an execution, given
  an input payload ID.
- `migrate` — described above.
- `query` — find state database records matching a filter, without
  fetching payload content from S3.
- `version` (top-level `cirrus version`, not under `manage`) — print the
  installed CLI version.

Management CLI commands that previously accepted user vars no longer
advertise support for them (user var support itself was removed back in
v1.0.0; the CLI's help text was inconsistent until this release).

## Library consumers

Code that imports `cirrus.lib` or `cirrus.management` directly should
review the following API changes.

### `cirrus.lib.statedb`

- `StateDB.get_dbitem()` now raises `PayloadNotFoundError` instead of
  returning `None` when no item matches the supplied ID.
- `StateDB.set_completed()` is renamed to `set_succeeded()`.
- `StateDB.dbitem_to_item()` changed from a classmethod to an instance
  method.
- `StateDB.payload_id_to_url()` and `StateDB.payload_key_to_url()` are
  removed. Use `StateDB.payload_id_to_input_payload_url()` or
  `StateDB.payload_id_to_output_payload_url()` instead.
- `StateDB.payload_id_to_bucket_key()` is removed.
- The standalone functions `get_payload_bucket()` and `get_state_db()` are
  removed from `cirrus.lib.statedb`.
- The state database item representation changed: the `catalog` field is
  renamed to `input_payload_url`; new `output_payload_url` and
  `claimed_at` fields are added. See the [State Database](70_statedb.md)
  reference for the current field list.

### Payload bucket access

- The new `PayloadBucket` class (`cirrus.lib.payload_bucket`) centralizes
  all S3 payload interactions. See the [Payload Bucket](75_payload_bucket.md)
  reference.
- `PayloadManager.upload_to_s3()` is removed. Use `PayloadBucket` methods
  instead.

### Exceptions

- `PayloadNotFoundError` moved from `cirrus.management.exceptions` to
  `cirrus.exceptions`.
- `NoExecutionsError` is removed from `cirrus.management.exceptions`,
  replaced by `ExecutionNotFoundError` in `cirrus.exceptions`.
- New exceptions: `ExecutionNotFoundError` and `PayloadNotFoundError` in
  `cirrus.exceptions`; `NoPayloadUrlError` in
  `cirrus.management.exceptions`; `UndefinedPayloadBucketError` in
  `cirrus.lib.errors`.

### `cirrus.management.deployment.Deployment`

- `Deployment.yield_payloads()` is removed, replaced by
  `Deployment.yield_workflow_items()` and
  `Deployment.yield_input_payloads()`.
- `Deployment.get_execution_arn()` no longer accepts an `arn` keyword
  argument; it now takes only `payload_id` as a positional parameter.
- `Deployment.fetch_payload()` signature changed: the `rerun` parameter is
  replaced with a `direction` parameter (`"input"` or `"output"`).
- `Deployment.enqueue_payload()` now explicitly accepts `dict`, `str`,
  `bytes`, or `IO[bytes]` payloads, with consistent handling across all
  types.
