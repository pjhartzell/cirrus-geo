# Lambda functions

Five Lambda functions ship with the core stack. They move payloads into and out of workflows, record state, and serve state over HTTP. `cloudformation/core/functions.yaml` creates each one as `${ResourcePrefix}-<name>` with a 15-second timeout and 256 MB of memory, from the handlers in `src/cirrus/lambda_functions/`.

| Function | Trigger | Role in the pipeline |
| --- | --- | --- |
| [`process`](#process) | The process SQS queue | Turns a queued payload into a Step Functions execution and records it as `PROCESSING` |
| [`update-state`](#update-state) | An EventBridge rule on execution status changes | Records the terminal state, publishes output items, enqueues chained payloads |
| [`pre-batch`](#pre-batch) | A workflow `Task` state before a Batch task | Uploads the payload to S3 so a Batch job can read it |
| [`post-batch`](#post-batch) | A workflow `Task` state after a Batch task | Returns the job's output payload to the state machine, or surfaces its error |
| [`api`](#api) | API Gateway | Read-only HTTP access to the state database and event metrics |

## process

### Queue trigger

An `AWS::Lambda::EventSourceMapping` delivers messages from the process queue in batches of up to ten. Anything that can send to that queue starts processing: a [feeder](../building-pipelines/feeders.md), the Cirrus CLI's `process` and `run-workflow` commands, and `update-state` when it enqueues the next payload in a [chain](../building-pipelines/chaining-workflows.md). One message carries one payload.

### Intake

For each record in the event, `lambda_handler` does the following, with the helpers named in `cirrus.lib.utils`.

1. **Normalize.** An event with a `Records` key is iterated record by record. Any other event is treated as a single record, which is how `invoke-lambda` submissions arrive.
2. **Extract** (`extract_record`). An SQS record's `body` is JSON-decoded. An SNS record's `Sns` object is taken. If the result has a `Message` key, that is JSON-decoded too, which unwraps an SNS envelope delivered through SQS. If the result has no `url` but has `Parameters.url_out`, it is a Batch job description and is replaced by `{"url": <url_out>}`. A record that raises here is announced as `RECORD_EXTRACT_FAILED`, uploaded to the payload bucket's invalid prefix, and counted as a failure.
3. **Fetch.** A `{"url": "s3://..."}` reference is replaced by the object it points at.
4. **Validate.** A `PayloadManager` is constructed with `set_id_if_missing=True`, which builds a `CirrusPayload`, generates an `id` from the items and workflow name if the payload has none, and calls `validate`. A payload that fails is announced as `NOT_A_PROCESS_PAYLOAD`, uploaded to the invalid prefix, and counted as a failure. See [Payload schema](payload-schema.md) for what validation checks.
5. **Decide and start** (`PayloadManagers.process`). The current state records for every payload in the batch are fetched with one `BatchGetItem`. Then, per payload:

   - A payload ID already handled in this batch is dropped, with a `DUPLICATE_ID_ENCOUNTERED` event.
   - A payload whose state is `FAILED`, `ABORTED`, `CLAIMED`, or absent, or whose process definition sets `replace`, is started.
   - Any other state is skipped, with an `ALREADY_PROCESSING`, `ALREADY_SUCCEEDED`, or `ALREADY_INVALID` event.

    The full table is in [The replace field and reruns](payload-schema.md#the-replace-field-and-reruns).

Starting a payload is three steps. `StateDB.claim_processing` writes `CLAIMED` under a condition that fails if the record is already `CLAIMED` or `PROCESSING`, which is what stops two concurrent invocations from starting the same execution. The input payload is uploaded to `<root>/executions/<payload_id>/<execution_id>/input.json`. Then `StartExecution` is called with the payload inline, or with a `{"url": ...}` reference to the oversized prefix when the escaped JSON exceeds 120,000 bytes. Finally `StateDB.set_processing` moves the record to `PROCESSING`.

The execution name is deterministic: a UUID5 of the payload ID and the record's existing `executions` list. Reprocessing a payload therefore produces a new name only because the list has grown. If the state machine named in the process definition does not exist, the payload is recorded `FAILED` with that error and the message is not retried.

### Batch outcome

If every record was handled, the invocation returns and SQS deletes the batch. If any record was rejected in steps 2 or 4, the invocation deletes the messages it did handle and then raises, so SQS redelivers only the rejected messages. After five receives they land on `${ResourcePrefix}-process-dlq`.

## update-state

### EventBridge trigger

The EventBridge rule `${ResourcePrefix}-update-state-sfn-events` matches `Step Functions Execution Status Change` events from `aws.states` whose `stateMachineArn` begins with `arn:aws:states:<region>:<account>:stateMachine:${ResourcePrefix}-` and whose status is `SUCCEEDED`, `FAILED`, `ABORTED`, or `TIMED_OUT`. The rule retries a failed invocation for up to 30 minutes and then sends the event to `${ResourcePrefix}-update-state-dlq`.

### Parsing the event

`Execution.from_event` reads the execution ARN, name, and status, and the input and output payloads embedded in the event. EventBridge omits the input when the escaped input and output together exceed 248 KiB, and omits the output as well when it alone exceeds that. The function raises if the input is missing, or if the status is `SUCCEEDED` and the output is missing, so an oversized output payload prevents the outcome from being recorded and the event ends on the dead-letter queue. Keeping payloads small avoids this; see [Payload bucket: Oversized payloads](payload-bucket.md#oversized-payloads).

### Status to state

| Execution status | Error type | Recorded state | Event |
| --- | --- | --- | --- |
| `SUCCEEDED` | | `SUCCEEDED` | `SUCCEEDED` |
| `FAILED` | `stactask.exceptions.InvalidInput` or `cirrus.lib.errors.InvalidInput` | `INVALID` | `INVALID` |
| `FAILED` | `TimedOutError` | `FAILED` | `TIMED_OUT` |
| `FAILED` | anything else | `FAILED` | `FAILED` |
| `TIMED_OUT` | set to `TimedOutError` | `FAILED` | `TIMED_OUT` |
| `ABORTED` | | `ABORTED` | `ABORTED` |

The error type comes from the event's `detail.error`. The message comes from `detail.cause`: if the cause is JSON with an `errorMessage` key, that value is used, otherwise the raw cause. The two are stored on the record as `<type>: <message>` in `last_error`. When the workflow's `Fail` state does not use `ErrorPath` and `CausePath`, the event carries no cause and a fixed message saying so is stored instead. See [Capturing errors](../building-pipelines/workflows.md#capturing-errors). The `cirrus.lib.errors.InvalidInput` name is matched as a string for tasks built against an older library; no such class exists in this package.

### On success

For a `SUCCEEDED` execution the function, in order:

1. Uploads the output payload to `<root>/executions/<payload_id>/<execution_id>/output.json`.
2. Records `SUCCEEDED` and emits the event.
3. Publishes each item in the output payload's `features` as one message to the publish topic, when `CIRRUS_PUBLISH_TOPIC_ARN` is set. Message attributes carry the item's `collection`, its `bbox` corners, `datetime`, `start_datetime`, and `end_datetime`, `eo:cloud_cover` as `cloud_cover`, and a `status` of `created` or `updated` derived from whether `created` and `updated` differ.
4. Enqueues the next payload or payloads of a chain onto the process queue, when `CIRRUS_PROCESS_QUEUE_URL` is set. See [Chaining workflows](../building-pipelines/chaining-workflows.md).

Step 2 runs before steps 3 and 4, so a failure to publish leaves the record `SUCCEEDED`.

## pre-batch

The function receives the state input, uploads it to `<root>/tmp/batch/<payload_id>/<uuid>.json`, and returns:

```json
{"url": "s3://<bucket>/<root>/tmp/batch/<payload_id>/<uuid>.json",
 "url_out": "s3://<bucket>/<root>/tmp/batch/<payload_id>/<uuid>_out.json"}
```

The Batch job reads its input from `url` and must write its output payload to `url_out`. The workflow passes both through the Batch task's `Parameters`. See [Batch tasks in a workflow](../building-pipelines/batch-workflow-structure.md).

## post-batch

The function receives the Batch task's output. When the job succeeded, that output carries the job's `Parameters`, which `extract_record` maps to `{"url": <url_out>}`. The function fetches the payload from that URL, validates it, and returns it to the state machine inline, or as a `{"url": ...}` reference to the oversized prefix if it exceeds the size limit, so the next task receives it the same way it would from a Lambda task.

When the job failed and the workflow's `Catch` routed the error into the input under `error`, the function reconstructs the job's own exception rather than passing on the generic Batch failure:

1. It reads `Attempts[-1].Container.LogStreamName` from the error's `Cause` and fetches that stream's last event from the `/aws/batch/job` log group.
2. It parses the line as `<ErrorType>: <message>` and raises an exception class created with that name, or `UnknownError` when the line has no type prefix.
3. If the stream cannot be read, typically because the container never started, it raises an exception carrying the container `Reason` and attempt `StatusReason` instead.

A `Cause` without attempts, a container, or a log stream name raises with a message naming the missing field.

## api

Serves the read-only HTTP API. It reads the state database, the data bucket's `catalog.json`, and the workflow metrics namespace, and never writes. See [HTTP API](http-api.md).

## IAM roles

Each function has its own role in `cloudformation/core/functions.yaml`. The grants are listed under [Deployment contract: IAM grants](deployment-contract.md#iam-grants).
