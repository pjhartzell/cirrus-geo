# Workflow events

A workflow event records a decision the `process` or `update-state` function made about one payload: claimed, started, skipped, rejected, or finished in a terminal state. Events are emitted by `WorkflowEventManager` (`cirrus.lib.events`), which each function constructs once per invocation. The methods that emit the started and terminal events also write the [state database](state-database.md) record, so the event stream and the state database agree by construction.

Events are not states. Several event types record a skip or rejection that leaves the state database untouched, and `TIMED_OUT` is an event type only: the state database records a timed-out execution as `FAILED`.

## Event types

`WFEventType` in `src/cirrus/lib/enums.py` defines the event types. The emit sites are `cirrus.lib.payload_manager` for the `process` function and `src/cirrus/lambda_functions/update_state.py` for `update-state`.

| Event type | Emitted by | When |
| --- | --- | --- |
| `CLAIMED_PROCESSING` | `process` | `StateDB.claim_processing` succeeded. A Step Functions execution is reserved for the payload but not yet started. |
| `STARTED_PROCESSING` | `process` | The execution was started and the record moved from `CLAIMED` to `PROCESSING`. |
| `ALREADY_PROCESSING` | `process` | The payload was skipped because its record is `PROCESSING`. |
| `ALREADY_SUCCEEDED` | `process` | Skipped because the record is `SUCCEEDED` and the process definition does not set `replace`. |
| `ALREADY_INVALID` | `process` | Skipped because the record is `INVALID` and `replace` is not set. |
| `ALREADY_CLAIMED` | none | Defined in the enum, but no current code path emits it. A payload whose record is `CLAIMED` is run against its pending execution rather than skipped. |
| `DUPLICATE_ID_ENCOUNTERED` | `process` | The same payload ID appeared more than once in the batch one invocation received. The later copy is dropped. |
| `RECORD_EXTRACT_FAILED` | `process` | No payload could be parsed from an incoming message. The raw message is uploaded to the payload bucket's invalid prefix, and `payload_id` is `unknown`. |
| `NOT_A_PROCESS_PAYLOAD` | `process` | A payload was parsed but `CirrusPayload.validate` rejected it. The message is uploaded to the invalid prefix. |
| `FAILED` | `update-state`, `process` | An execution ended `FAILED` with an error type that is neither an `InvalidInput` class nor `TimedOutError`. Also emitted by `process` when starting the execution fails, for example because the named state machine does not exist. |
| `TIMED_OUT` | `update-state` | Execution status `TIMED_OUT`, or status `FAILED` with error type `TimedOutError`. |
| `INVALID` | `update-state` | Execution status `FAILED` with error type `stactask.exceptions.InvalidInput`, or the name `cirrus.lib.errors.InvalidInput`, which is matched as a string for tasks built against older libraries. |
| `SUCCEEDED` | `update-state` | Execution status `SUCCEEDED`. |
| `ABORTED` | `update-state` | Execution status `ABORTED`. |

`RECORD_EXTRACT_FAILED` and `NOT_A_PROCESS_PAYLOAD` both mean `process` rejected a message before any workflow could start. The first fires when the message itself cannot be turned into a payload object, the second when a payload object was built but failed validation. See [Lambda functions: process](lambda-functions.md#process) for the intake sequence.

## Event fields

`WorkflowEvent` carries these fields. The serialized message omits any field that is unset, and replaces `execution_arn` with `execution`, the Step Functions console URL for that ARN.

| Field | Set on |
| --- | --- |
| `event_type` | Every event. |
| `payload_id` | Every event. `unknown` on `RECORD_EXTRACT_FAILED`, and on `NOT_A_PROCESS_PAYLOAD` when the parsed object has no `id`. |
| `isotimestamp` | Every event. UTC, ISO 8601. |
| `input_payload_url` | `STARTED_PROCESSING`, most `ALREADY_*` skips, `DUPLICATE_ID_ENCOUNTERED`, and the terminal events. On the two rejection events it is the URL of the uploaded raw message under the invalid prefix. Never set on `CLAIMED_PROCESSING`, which fires before the input payload is uploaded. |
| `output_payload_url` | `SUCCEEDED`, and `ALREADY_SUCCEEDED`. |
| `execution` | `STARTED_PROCESSING` and the terminal events. |
| `error` | `FAILED`, `TIMED_OUT`, `INVALID`, and the two rejection events. For terminal events the value is `<error type>: <message>` as extracted by `update-state`. |

## Destinations

`WorkflowEventManager.announce` sends each event to up to two destinations. Both are optional and independently configured by environment variables that `cloudformation/core/functions.yaml` sets on the `process` and `update-state` functions.

### Workflow event topic

When `CIRRUS_WORKFLOW_EVENT_TOPIC_ARN` is set, events are published to that SNS topic. The reference templates create it as `${ResourcePrefix}-workflow-event` in `cloudformation/core/base.yaml`. Publishes are batched, up to ten per request, and flushed when the invocation ends.

The message body is the serialized event. Message attributes carry `event_type`, and, when the payload ID parses, `workflow` and `collections`, plus `error` when the event has one. A subscription filter policy on these attributes can select, for example, only `FAILED` events for one workflow.

### CloudWatch log group and metrics

When `CIRRUS_WORKFLOW_LOG_GROUP` is set, `WorkflowMetricLogger` writes each event as one JSON log line, immediately, to a log stream named `workflow-metrics-<uuid>` that it creates per invocation. The line holds `event`, `workflow`, `source` (the collections segment of the payload ID), and `execution_arn`. A payload ID that does not match the ID format is logged with `workflow` set to `could not parse` and `source` set to the raw ID.

The metrics stack (`cloudformation/core/metrics.yaml`, created when the main stack's `EnableWorkflowMetrics` parameter is `true`, its default) provides:

| Resource | Name | Notes |
| --- | --- | --- |
| Log group | `${ResourcePrefix}-workflow-event-metrics` | One-day retention. |
| Metric filter | `all_workflows_by_event` | Namespace `${ResourcePrefix}-workflow`, dimension `event`, value 1 per line. |
| Metric filter | `a_workflow_by_event` | Same namespace, dimensions `event` and `workflow`. |

The main stack passes the log group name to `process` and `update-state` as `CIRRUS_WORKFLOW_LOG_GROUP` and the namespace to `api` as `CIRRUS_WORKFLOW_METRIC_NAMESPACE`, which `WorkflowMetricReader` uses to serve the HTTP API's [`/stats`](http-api.md#stats) endpoint. When `EnableWorkflowMetrics` is `false`, both variables are empty strings, no events are logged, and `/stats` returns 404 unless the deprecated Timestream path below is configured.

### Timestream event database, deprecated

`EventDB` (`cirrus.lib.eventdb`) writes to an Amazon Timestream table named by `CIRRUS_EVENT_DB_AND_TABLE` as `DATABASE|TABLE`. No template in `cloudformation/` sets that variable. When it is set, `WorkflowEventManager` emits a `DeprecationWarning` at construction and writes one record for `STARTED_PROCESSING` and for each terminal event. Claims, skips, duplicates, and rejections are not written. The record's measure value is the state name, except that `SUCCEEDED` is written as `COMPLETED` and `TIMED_OUT` as `INVALID`. The `/stats` endpoint reads Timestream only when CloudWatch metrics are disabled.

## Reading events

- Subscribe a queue, function, or email endpoint to the workflow event topic.
- Query the `${ResourcePrefix}-workflow` metrics namespace directly in CloudWatch, or build alarms on it. See [Monitoring](../operating/monitoring.md).
- Call the HTTP API's `/stats` endpoint for daily and hourly counts by state.

The Cirrus CLI has no command that reads events.
