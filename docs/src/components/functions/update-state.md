# update-state

The `update-state` Lambda function records the results of Step Functions
workflow executions in the DynamoDB state database, and drives the
post-workflow actions: publishing output items to SNS and enqueuing chained
payloads.

## Trigger

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
captured (see [workflow definitions](../workflows/definitions.md)).

The execution's input and output payloads are read from the EventBridge
event itself. If the combined size exceeds the EventBridge limit the payloads
are excluded from the event and the function raises an error.

## Actions on completion

Every invocation updates the state database record and emits a workflow
event to the event recording system. For successful executions,
`update-state` additionally:

- uploads the output payload to the payload bucket
- publishes each output item to the publish SNS topic (when
  `CIRRUS_PUBLISH_TOPIC_ARN` is configured), for consumption by downstream
  services such as a STAC API ingest
- enqueues any chained payloads onto the process queue (when
  `CIRRUS_PROCESS_QUEUE_URL` is configured), continuing a
  [workflow chain](../workflows/chaining.md)
