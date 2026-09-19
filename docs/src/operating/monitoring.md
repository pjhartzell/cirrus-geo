# Monitoring

A Cirrus deployment exposes four places to look when tracking work: the state database for per-payload state, the workflow event stream for aggregate counts and alerting, the Step Functions execution for what happened inside a workflow, and CloudWatch Logs for task and function output. This page says what each one holds and how to reach it. Command syntax is in [Common workflows](../cli/common-workflows.md).

## State database

The [state database](../reference/state-database.md) holds one record per payload ID. The fields to read first are `state_updated`, whose prefix is the current state, `last_error`, present on `FAILED` and `INVALID` records, and `executions`, the list of Step Functions execution ARNs attempted for the payload, most recent last.

The Cirrus CLI reads records with `get-state` for one payload ID, `query` for records matching a collections-workflow, state, time window, or error prefix, and `get-input-payloads` for the input payloads behind those records. See [Check state and stored payloads](../cli/common-workflows.md#check-state-and-stored-payloads) and [Query the state database in bulk](../cli/common-workflows.md#query-the-state-database-in-bulk).

The same records are readable over HTTP through the [HTTP API](../reference/http-api.md), which also returns per-state counts for a collections-workflow.

## Workflow events

Every claim, start, skip, rejection, and terminal outcome is emitted as a [workflow event](../reference/workflow-events.md). Three uses for an operator:

- **Alerting.** Subscribe to the `${ResourcePrefix}-workflow-event` SNS topic with a filter policy on the `event_type` message attribute, for example `FAILED` and `INVALID` only.
- **Dashboards and alarms.** With the metrics stack enabled, the `${ResourcePrefix}-workflow` CloudWatch namespace holds a count per event type and per workflow. A CloudWatch alarm on `all_workflows_by_event` with dimension `event=FAILED` fires on failures across the deployment.
- **Aggregate counts.** The HTTP API's [`/stats`](../reference/http-api.md#stats) endpoint returns daily and hourly counts by state from the same metrics.

## Step Functions executions

Each workflow is a Step Functions state machine named `${ResourcePrefix}-<workflow>`. The AWS console's execution detail view shows the state graph, each state's input and output, and the event history.

A state database record's `executions` field holds the raw execution ARNs. Records returned by `query`, `get-input-payloads`, and the HTTP API pass through `StateDB.dbitem_to_item`, which converts each ARN to a console URL. `get-state` returns the raw record, so its ARNs are unconverted.

The CLI reads an execution without the console. `get-execution`, `get-execution-input`, `get-execution-output`, and `get-execution-events` each take either `--arn` or `--payload-id`, and a payload ID resolves to its most recent execution. `get-execution-events --with-log-metadata` adds a `logMetadata` object to each `TaskSucceeded` and `TaskFailed` event for Lambda and Batch tasks: the log group and Lambda request ID, or the Batch log stream name, that the task's logs are under. See [Inspect an execution](../cli/common-workflows.md#inspect-an-execution).

## CloudWatch logs

Each framework function writes to the standard Lambda log group `/aws/lambda/<function-name>`, where the function name is `${ResourcePrefix}-<name>`:

| Function | Log group |
| --- | --- |
| [`api`](../reference/lambda-functions.md#api) | `/aws/lambda/${ResourcePrefix}-api` |
| [`process`](../reference/lambda-functions.md#process) | `/aws/lambda/${ResourcePrefix}-process` |
| [`update-state`](../reference/lambda-functions.md#update-state) | `/aws/lambda/${ResourcePrefix}-update-state` |
| [`pre-batch`](../reference/lambda-functions.md#pre-batch) | `/aws/lambda/${ResourcePrefix}-pre-batch` |
| [`post-batch`](../reference/lambda-functions.md#post-batch) | `/aws/lambda/${ResourcePrefix}-post-batch` |

Lambda tasks follow the same convention under their own function names. AWS Batch jobs log to the shared `/aws/batch/job` log group, one stream per job attempt. The `post-batch` function reads the last line of that stream to reconstruct a failed job's error.

### Isolating one Lambda invocation

All invocations of a function write to one log group, and a reused execution environment writes several invocations to the same log stream, so the stream alone does not isolate one run. Each invocation has a unique request ID. For a task invoked through the `arn:aws:states:::lambda:invoke` resource, Step Functions records that ID in the execution history: in `SdkResponseMetadata.RequestId` of a `TaskSucceeded` event's output, and in the `requestId` of a `TaskFailed` event's cause. `get-execution-events --with-log-metadata` extracts it, and `get-lambda-logs` filters the log group by it:

```bash
cirrus manage name-dev get-execution-events --payload-id <payload-id> --with-log-metadata
cirrus manage name-dev get-lambda-logs /aws/lambda/name-dev-my-task <request-id>
```

The equivalent AWS CLI call is a filter on the request ID string:

```bash
aws logs filter-log-events \
    --log-group-name /aws/lambda/name-dev-my-task \
    --filter-pattern '"<request-id>"'
```

Log lines written through `CirrusLoggerAdapter` also carry the payload `id` as a JSON field, which filters a task's output by payload rather than by invocation. See [Structured logging](../building-pipelines/tasks.md#structured-logging).

For a Batch job, `get-batch-logs <log-stream>` reads the job's stream from `/aws/batch/job`.

## Dead-letter queues

`cloudformation/core/base.yaml` creates two dead-letter queues, both with 14-day retention. Messages arriving on either are worth an alarm.

- **`${ResourcePrefix}-process-dlq`** receives a process queue message after five failed receives. `process` raises when any message in its batch cannot be turned into a valid payload, after deleting the messages it did handle, so only the rejected messages are retried and eventually dead-lettered.
- **`${ResourcePrefix}-update-state-dlq`** is the dead-letter target of the EventBridge rule that invokes `update-state`. EventBridge retries a failed invocation for up to 30 minutes (`MaximumEventAgeInSeconds: 1800` in `cloudformation/core/functions.yaml`) before sending the event here. An event on this queue means an execution finished but its outcome was never recorded in the state database.

## Rerunning payloads

`get-input-payloads --rerun` returns each matching input payload with `replace: true` set on its first process definition, so `process` accepts it for a fresh execution from states it would otherwise skip. Which states run by default and which need `replace` is defined in [The replace field and reruns](../reference/payload-schema.md#the-replace-field-and-reruns). The resubmission loop is in [Rerun failed workflows in bulk](../cli/common-workflows.md#rerun-failed-workflows-in-bulk).
