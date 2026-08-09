# Monitoring

Tracking the state of workflow executions is essential for pipeline
monitoring — knowing what succeeded, what failed, and why. Cirrus surfaces
this information through four channels: the state database, workflow events
(CloudWatch metrics and, optionally, Timestream), the AWS Step Functions
console, and CloudWatch Logs.

## Querying the state database

The [state database](../reference/state-database.md) (StateDB) is a DynamoDB table that
records the current state of every payload a deployment has processed. The
Cirrus CLI queries it directly through the `manage` command group.

`get-state` fetches the raw record for a single payload by its payload ID:

```bash
cirrus manage DEPLOYMENT_NAME get-state sar/workflow-test/example-01_2024-10-31-06-05-10
```

`query` filters records by collections/workflow, state, and time window, and
streams matching StateDB records as newline-delimited JSON:

```bash
cirrus manage DEPLOYMENT_NAME query \
    --collections-workflow "sar-test_flow" \
    --state FAILED \
    --since 7d
```

`get-input-payloads` accepts the same filters but resolves each match to its
input payload in the payload bucket and streams the payloads themselves —
useful for feeding failed payloads back into `process` for a rerun with the
`--rerun` flag. See [Rerunning payloads](#rerunning-payloads) below.

All three commands accept the same filter set: `--collections-workflow`
(required), `--state` (one of `PROCESSING`, `SUCCEEDED`, `FAILED`,
`INVALID`, `ABORTED`, `CLAIMED`), `--since` (an integer followed by `d`, `h`,
or `m`, e.g. `7d`, `24h`, `30m`), `--limit`, and `--error-prefix` (filters on
the stored error message prefix). See the [CLI reference](../cli/common-workflows.md)
for full option details and the [state database reference](../reference/state-database.md) for
the record schema and state meanings.

## Workflow events

Every state transition — a payload being claimed, started, succeeded,
failed, marked invalid, aborted, or skipped as a duplicate — is recorded as a
workflow event by `WorkflowEventManager` (`cirrus.lib.events`), called from
the `process` and `update-state` functions. The full set of event types
(`WFEventType` in `cirrus.lib.enums`):

| Event type | Recorded when |
| --- | --- |
| `CLAIMED_PROCESSING` | A payload is claimed in the state database ahead of starting a Step Functions execution. |
| `STARTED_PROCESSING` | The claimed execution actually starts. |
| `ALREADY_CLAIMED` | `process` skips a payload already in the `CLAIMED` state. |
| `ALREADY_PROCESSING` | `process` skips a payload already in the `PROCESSING` state. |
| `ALREADY_SUCCEEDED` | `process` skips a payload already in the `SUCCEEDED` state (unless `replace` applies — see [Rerunning payloads](#rerunning-payloads)). |
| `ALREADY_INVALID` | `process` skips a payload already in the `INVALID` state (unless `replace` applies). |
| `DUPLICATE_ID_ENCOUNTERED` | A duplicate payload ID is dropped during processing. |
| `SUCCEEDED` | `update-state` records a successful Step Functions execution. |
| `FAILED` | `update-state` records a failed execution whose error type is neither an invalid-input error nor a timeout. |
| `TIMED_OUT` | `update-state` records an execution that timed out (Step Functions `TIMED_OUT` status, or a `FAILED` status whose error type is `TimedOutError`). |
| `INVALID` | `update-state` records a failed execution whose error type is `cirrus.lib.errors.InvalidInput` or `stactask.exceptions.InvalidInput`. |
| `ABORTED` | `update-state` records an aborted execution. |
| `RECORD_EXTRACT_FAILED` | `process` cannot pull a payload out of the raw incoming message — `utils.extract_record` raises before any payload JSON exists (malformed SQS/SNS envelope, for example). No payload ID is available yet. |
| `NOT_A_PROCESS_PAYLOAD` | `process` extracted a payload from the message, but the extracted content isn't a valid Cirrus payload — constructing a `PayloadManager` from it raises (missing `id`, malformed `process` block, etc.). |

`RECORD_EXTRACT_FAILED` and `NOT_A_PROCESS_PAYLOAD` are easy to confuse: both
mean `process` rejected an incoming message before a workflow could start,
but the first fires when the message itself can't be parsed into a payload,
and the second fires when a payload was parsed but fails validation as a
Cirrus payload.

`FAILED`, `TIMED_OUT`, and `INVALID` are also related — all three originate
from a Step Functions execution that did not succeed, and `update-state`
distinguishes them only by inspecting the execution's error type. A timeout
inside the state machine surfaces as Step Functions status `TIMED_OUT`, but a
task that raises its own timeout error before the state machine's own timer
fires shows up as status `FAILED` with error type `TimedOutError`; both are
recorded as `TIMED_OUT`. Note that `TIMED_OUT` is only an event type, not a
state — the state database records a timed-out execution as `FAILED`.

Each event carries the payload ID, a timestamp, and — where applicable — the
Step Functions execution ARN, input/output payload URLs, and an error
message.

### Where events go

`WorkflowEventManager.announce` fans each event out to up to two
destinations, both optional and independently configured:

- **SNS** — if `CIRRUS_WORKFLOW_EVENT_TOPIC_ARN` is set, the event is
  published to the workflow event topic.
- **CloudWatch** — if `WorkflowMetricLogger` is enabled (its log group name
  comes from `CIRRUS_WORKFLOW_LOG_GROUP`), the event is written as a JSON log
  line to a per-invocation log stream in that log group. CloudWatch Logs
  metric filters (`cloudformation/core/metrics.yaml`) convert those log lines
  into two CloudWatch metrics in the `<ResourcePrefix>-workflow` namespace:
  `all_workflows_by_event` (dimensioned by `event`) and
  `a_workflow_by_event` (dimensioned by `event` and `workflow`).
  `WorkflowMetricReader` reads these metrics back out.

This CloudWatch path is provisioned by the `metrics.yaml` nested stack, which
is only created when the deployment's top-level `EnableWorkflowMetrics`
CloudFormation parameter is `true` (the default). When disabled, the
`WorkflowMetricLogGroup`/`WorkflowMetricNamespace` parameters passed to the
functions stack are empty strings and both `WorkflowMetricLogger` and
`WorkflowMetricReader` report themselves as not enabled.

!!! note "Timestream EventDB is deprecated"
    `cirrus.lib.eventdb.EventDB` writes the same state-transition events to a
    Timestream database and table, configured via the `CIRRUS_EVENT_DB_AND_TABLE`
    environment variable (a pipe-separated `database|table` value; unset means
    disabled). `WorkflowEventManager` still writes to it when configured, but
    emits a `DeprecationWarning` in favor of the CloudWatch metrics path.
    Support for the Timestream path is expected to be removed in a future
    release.

### Reading events back

The [`api` function](../reference/lambda-functions.md#api)'s `/stats` endpoint
returns aggregate event counts grouped by state, on daily, hourly, and
rolling-hour bases. It reads from CloudWatch metrics when
`WorkflowMetricReader` is enabled, falling back to the Timestream event
database, and returns a 404 if neither is configured.

## Step Functions console

Every workflow is a Step Functions state machine named
`<ResourcePrefix>-<workflow>`. The AWS Console's Step Functions page lists
executions per state machine, and each execution's detail view shows its
graph, input/output payloads, and event history.

The state database record for a payload (see
[state database fields](../reference/state-database.md#fields)) stores the Step Functions
execution ARNs for every execution attempted for that payload in its
`executions` field — a payload rerun after a failure accumulates multiple
entries. Records returned by `query`, `get-input-payloads`, and the `api`
function convert these ARNs to direct console URLs
(`https://<region>.console.aws.amazon.com/states/home?region=<region>#/v2/executions/details/<execution-arn>`);
`get-state` returns the raw ARNs. The Cirrus CLI's `get-execution`,
`get-execution-input`, `get-execution-output`, and `get-execution-events`
commands resolve either an execution ARN or a payload ID (which resolves to
its most recent execution) to query the execution directly, without opening
the console:

```bash
cirrus manage DEPLOYMENT_NAME get-execution --payload-id sar/workflow-test/example-01_2024-10-31-06-05-10
cirrus manage DEPLOYMENT_NAME get-execution-events --arn arn:aws:states:us-west-2:000000000011:execution:fd-name-dev-cirrus-project:c123456789-b19292-999
```

## CloudWatch logs per function

Each Lambda function writes to its own log group, following the standard
AWS Lambda convention `/aws/lambda/<function-name>`. Function names are
`<ResourcePrefix>-<name>` (from `cloudformation/core/functions.yaml`):

| Function | Log group |
| --- | --- |
| [`api`](../reference/lambda-functions.md#api) | `/aws/lambda/<ResourcePrefix>-api` |
| [`process`](../reference/lambda-functions.md#process) | `/aws/lambda/<ResourcePrefix>-process` |
| [`update-state`](../reference/lambda-functions.md#update-state) | `/aws/lambda/<ResourcePrefix>-update-state` |
| [`pre-batch`](../reference/lambda-functions.md#pre-batch) | `/aws/lambda/<ResourcePrefix>-pre-batch` |
| [`post-batch`](../reference/lambda-functions.md#post-batch) | `/aws/lambda/<ResourcePrefix>-post-batch` |

AWS Batch jobs (run by [Batch tasks](../building-pipelines/batch-infrastructure.md), not by
the `pre-batch`/`post-batch` functions themselves) log to the shared
`/aws/batch/job` log group, one log stream per job attempt. The `post-batch`
function reads from this log group directly to extract the error from a
failed job's last log line.

The Cirrus CLI's `get-lambda-logs` and `get-batch-logs` commands fetch
CloudWatch logs for a specific invocation or job without using the console.
See [Lambda logs](../building-pipelines/tasks.md#lambda-logs) for the
request-ID filtering pattern that isolates a single invocation's logs, and
the [CLI reference](../cli/common-workflows.md) for full command usage.

## Rerunning payloads

A common recovery action is to re-run payloads after fixing whatever caused
them to fail — a task bug, bad input, a transient AWS error. `get-input-payloads
--rerun` resolves matching state database records back to their input
payloads and marks each one so `process` will accept it for a fresh
execution from states that would otherwise be skipped:

```bash
cirrus manage DEPLOYMENT_NAME get-input-payloads \
    --collections-workflow "sar-test_workflow" --state FAILED --since 7d --rerun |
while IFS= read -r payload; do
    printf '%s' "$payload" | cirrus manage DEPLOYMENT_NAME process
done
```

`--rerun` sets `process[0].replace: true` on each returned payload. `process`
enqueues one payload per invocation, so the output — NDJSON, one payload per
line — is submitted line by line rather than piped in bulk. See the
[CLI reference](../cli/reference.md) or the
[query-the-state-database-in-bulk workflow](../cli/common-workflows.md#query-the-state-database-in-bulk)
for the full set of `get-input-payloads` filters.

Which recorded states actually restart a workflow, and exactly what
`replace: true` changes, is defined once, canonically, in
[The replace field and reruns](../reference/payload-schema.md#the-replace-field-and-reruns).
