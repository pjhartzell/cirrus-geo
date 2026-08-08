# Lambda functions

The `function` component type refers to the AWS Lambda functions built into
Cirrus. These functions wrap the workflows and tasks: they move payloads into
and out of workflows, track state, and expose deployment data over HTTP. All
five are created by the CloudFormation core stack.

- [`process`](#process): consumes payloads from the process SQS queue,
  records them in the state database, and starts workflow Step Functions
  executions.
- [`update-state`](#update-state): handles Step Functions execution
  completion events, updating the state database, publishing notifications,
  and enqueuing chained payloads.
- [`pre-batch`](#pre-batch): runs before a Batch task in a workflow,
  uploading the input payload to S3 and returning its URL for the Batch job.
- [`post-batch`](#post-batch): runs after a Batch task in a workflow,
  retrieving the task output payload from S3; on job failure it retrieves the
  error from the Batch job logs and re-raises it in the Step Functions
  context.
- [`api`](#api): a read-only HTTP API for querying workflow state and event
  metrics, e.g., for monitoring dashboards.

## process

The `process` Lambda function is the entry point into Cirrus workflows. It
consumes messages from the process SQS queue, extracts a Cirrus Payload from
each message, records the payload in the state database, and starts a Step
Functions execution of the workflow named in the payload's process
definition.

### Trigger

The process SQS queue is the function's event source. Anything that can put a
message on that queue can trigger processing:

- a [feeder](../building-pipelines/feeders.md) publishing payloads to the queue (directly
  or via the process SNS topic)
- the Cirrus CLI `process` command, which enqueues a payload read from stdin:

        cirrus manage DEPLOYMENT_NAME process < payload.json

A single message carries a single payload; bulk processing is a matter of
sending many messages, which the function consumes in SQS batches.

### Payload extraction

Each message may contain a Cirrus Payload directly, an SNS notification
wrapping a payload, or an object with a `url` field pointing to a payload in
S3, in which case the payload is fetched from S3. Messages from which no
payload can be extracted, or whose payload is not a valid process payload,
are recorded as workflow events (`RECORD_EXTRACT_FAILED` or
`NOT_A_PROCESS_PAYLOAD`), their content is uploaded to the payload bucket for
inspection, and the batch fails so unprocessable messages fall through to the
dead-letter queue.

### State management and workflow start

For each payload, the function:

1. Claims the payload in the state database (state `CLAIMED`), which locks
   out concurrent duplicate executions. Payloads already in `PROCESSING` are
   skipped, as are payloads in `SUCCEEDED` or `INVALID` unless the process
   definition sets `replace: true`. Payloads in `FAILED`, `ABORTED`, or
   `CLAIMED` states are (re)run.
2. Uploads the input payload to the payload bucket.
3. Starts the Step Functions execution and transitions the state database
   record from `CLAIMED` to `PROCESSING`.

If some payloads in an SQS batch fail, the successfully processed messages
are deleted from the queue and the invocation raises an error so only the
failed messages are retried.

## update-state

The `update-state` Lambda function records the results of Step Functions
workflow executions in the DynamoDB state database, and drives the
post-workflow actions: publishing output items to SNS and enqueuing chained
payloads.

### Trigger

An EventBridge rule invokes `update-state` whenever a workflow Step Functions
execution reaches a terminal status. The terminal execution statuses are a
Step Functions concept, distinct from (but mapped to) the state database
states:

| Execution status | Resulting state database state |
| ---------------- | ------------------------------ |
| `SUCCEEDED`      | `SUCCEEDED`                    |
| `FAILED`         | `FAILED` or `INVALID`          |
| `ABORTED`        | `ABORTED`                      |
| `TIMED_OUT`      | `FAILED`                       |

A `FAILED` execution is recorded as `INVALID` when its error type is
`stactask.exceptions.InvalidInput` — or `cirrus.lib.errors.InvalidInput`,
the equivalent exception from pre-2.0 cirrus-lib, still recognized so tasks
built against the old library classify correctly; a
`TIMED_OUT` execution is recorded as `FAILED` with a `TimedOutError` error.
For failed executions, the error name and cause are extracted from the event
and stored on the state database record. The workflow definition's `Fail`
state must include `ErrorPath` and `CausePath` fields for the cause to be
captured (see [workflow definitions](../building-pipelines/workflows.md)).

The execution's input and output payloads are read from the EventBridge
event itself. If the combined size exceeds the EventBridge limit the payloads
are excluded from the event and the function raises an error.

### Actions on completion

Every invocation updates the state database record and emits a workflow
event to the event recording system. For successful executions,
`update-state` additionally:

- uploads the output payload to the payload bucket
- publishes each output item to the publish SNS topic (when
  `CIRRUS_PUBLISH_TOPIC_ARN` is configured), for consumption by downstream
  services such as a STAC API ingest
- enqueues any chained payloads onto the process queue (when
  `CIRRUS_PROCESS_QUEUE_URL` is configured), continuing a
  [workflow chain](../building-pipelines/chaining-workflows.md)

## pre-batch

The `pre-batch` Lambda function runs immediately before a Batch task in a
workflow, working around an AWS Batch limitation: a Batch job submission
cannot carry a large JSON payload directly, and Cirrus Payloads can be large.

`pre-batch` uploads the input payload to the payload bucket and returns:

- `url`: the S3 URL of the uploaded input payload, passed to the Batch job
  as its input parameter
- `url_out`: the S3 URL (the input URL with an `_out.json` suffix) where the
  Batch task must write its output payload, picked up afterwards by
  [`post-batch`](#post-batch)

## post-batch

The `post-batch` Lambda function runs immediately after a Batch task in a
workflow, performing the inverse of [`pre-batch`](#pre-batch): it reads the
task's output payload from S3 (at the `url_out` location established by
`pre-batch`) and returns it to the Step Functions state machine, so the next
task receives it the same way it would from a Lambda task.

### Error handling

When the Batch job fails, `post-batch` reconstructs the underlying error so
it surfaces in the Step Functions execution rather than a generic Batch
failure:

1. It reads the last log event from the job's final attempt in the
   `/aws/batch/job` CloudWatch log group.
2. It parses the error type and message from that log line and re-raises the
   error under the original type name (falling back to `UnknownError`).
3. If the log stream cannot be read — typically because the container never
   started — it raises an error carrying the Batch container reason and
   attempt status reason instead (e.g. `DockerTimeoutError`, "Task failed to
   start").

## api

The `api` Lambda function serves a read-only HTTP API over the state
database and workflow event metrics. It supports uses like monitoring
dashboards that need aggregate event statistics, and sits outside the payload
flow shown in the [architecture diagram](../getting-started/architecture.md) — unlike
the other functions, it never modifies state.

See the [Cirrus API endpoints reference](http-api.md)
for the endpoint surface, full request/response shapes, error behavior, and
how the API is exposed via CloudFormation.
