# Possibly-unintended code behaviors

Behaviors surfaced by the docs audits (2026-08 and 2026-09) that look unintended but are
documented as-written where user-visible. Docs-branch policy is no code
edits, so these are recorded here for follow-up. Each fix is a code change
that requires a docs follow-up where a page is cited.

## api Lambda (`src/cirrus/lambda_functions/api.py`)

- **`urljoin(None)` on missing `domainName`** (`api.py:274-280`). If API
  Gateway supplies no `requestContext.domainName`, `root_url` is `None` and
  `get_root` calls `urljoin(None, ...)`, which raises. Likely dead code for
  real `AWS_PROXY` events; not reachable to verify from docs work.
- **Literal `items` route shadowing** (`api.py:337`). The item-ID path
  segment is matched against the literal string `"items"` to select the
  paginated items route, so a payload whose item-ID segment is literally
  `items` is shadowed and cannot be fetched individually.
- ~~Dropped `nextkey` pagination token~~ Fixed on main in #374; the items
  route now returns `nextkey` when more results exist.

## Workflow events (`src/cirrus/lib/events.py`)

- **`timed_out` writes its Timestream record as `INVALID`**
  (`events.py:688-694`). `WorkflowEventManager.timed_out` calls
  `statedb.set_failed` (state database records `FAILED`, consistent with
  `update-state`'s documented mapping) but passes `StateEnum.INVALID` to
  `_write_timeseries_record`. Likely a copy-paste error from the `invalid`
  method. Low impact — the Timestream event DB is deprecated — but the
  record written disagrees with the state recorded.

## process Lambda and payload manager (`src/cirrus/lib/payload_manager.py`, `lambda_functions/process.py`)

- **`ALREADY_CLAIMED` is never emitted.** `PayloadManagers.process` runs a
  payload whose record is `CLAIMED`, and `PayloadManager._claim` resolves a
  `CLAIMED` condition failure against the stored execution rather than
  skipping, so no path reaches `skipping(state=CLAIMED)`. The event type
  remains in `WFEventType`. Documented as unreachable in
  `docs/src/reference/workflow-events.md`.
- **`skipping` has no mapping for `FAILED` or `ABORTED`.**
  `WorkflowEventManager.skipping` indexes `state2event` with the record's
  state; the dict covers only `INVALID`, `PROCESSING`, `CLAIMED`, and
  `SUCCEEDED`. `PayloadManager.__call__` calls it with whatever state the
  record has when `set_processing`'s condition fails, which happens when the
  execution finishes and `update-state` writes a terminal state before
  `process` writes `PROCESSING`. A very short workflow (the in-repo
  `minimal` workflow) can hit this, raising `KeyError` out of the handler
  and retrying the whole SQS batch.
- **A `StateMachineDoesNotExist` failure is not dead-lettered.** The code
  comment on the `TerminalError` path says the intent is for the message to
  fall through to the DLQ, but the payload ID is added to `processed["failed"]`,
  which `lambda_handler` treats as handled: the SQS message is deleted before
  the handler raises. The record is marked `FAILED`; the message is not
  retried. Documented as-written in `docs/src/reference/lambda-functions.md`.

## update-state Lambda (`src/cirrus/lambda_functions/update_state.py`)

- **The state record's `outputs` field is never written.**
  `workflow_succeeded` calls `WorkflowEventManager.succeeded`, which calls
  `StateDB.set_succeeded` without `outputs`; nothing calls
  `StateDB.set_outputs`. The field is still removed on claim and still
  described in the schema. Documented as unused in
  `docs/src/reference/state-database.md`.

## Migration (`src/cirrus/management/migration.py`)

- **`last_error` is removed from `INVALID` records.**
  `MigrationRecord.build_db_update_plan` removes `last_error` when the state
  is anything other than `FAILED`, but `StateDB.set_invalid` writes
  `last_error` too, so migrating a 1.x `INVALID` record discards its error.

## CLI validation (`src/cirrus/lib/cirrus_payload.py`, `management/`)

- **`validate` raises `KeyError`, not a validation error, on a payload
  without `id`.** `CirrusPayload.validate` does `PAYLOAD_ID_REGEX.match(self["id"])`.
  `process` avoids this by constructing with `set_id_if_missing=True`, but
  `Deployment.run_workflow` and `cirrus payload validate` construct without
  it, so an ID-less payload fails those commands with a `KeyError` traceback
  rather than a message. Documented as a requirement for an `id` in
  `docs/src/cli/common-workflows.md`.

## run-workflow on a rerun (`src/cirrus/management/deployment.py`)

- **`run_workflow` returns the previous outcome when the record is
  already terminal.** After enqueuing, it polls `get_payload_state` while
  the state is `PROCESSING`. A payload resubmitted with `replace: true`
  whose record is `SUCCEEDED`, `FAILED`, `INVALID`, or `ABORTED` from an
  earlier run exits the loop on the first poll, before `process` has
  claimed the rerun, and the command prints the earlier run's output
  payload with exit code 0. Observed 2026-09-20 on LocalStack: the record
  showed one execution when the command returned and two a few seconds
  later. Documented on the first-pipeline tutorial and the CLI cookbook.

## CLI on LocalStack (`src/cirrus/management/task_logs.py`)

- **`get-execution-events --with-log-metadata` raises `KeyError`
  on LocalStack.** `_extract_lambda_metadata` reads
  `output["SdkResponseMetadata"]["RequestId"]` from a `TaskSucceeded`
  event; LocalStack's Step Functions emulation omits `SdkResponseMetadata`
  from the `lambda:invoke` output, so the command fails with a traceback
  rather than skipping the event. Observed 2026-09-20 on
  localstack/localstack:4. Documented on the first-pipeline tutorial.

## Templates and scripts

- **`EnableWorkflowMetrics` parameter description** in
  `cloudformation/main.yaml` reads "Enable VPC creation and Lambda VPC
  configuration", copied from `EnableVpc`.
- **`localstack-provision.bash debootstrap`** waits on
  `stack-delete-complete` for `MAIN_STACK` after deleting `BOOTSTRAP_STACK`.
