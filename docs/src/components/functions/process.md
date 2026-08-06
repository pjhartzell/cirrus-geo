# process

The `process` Lambda function is the entry point into Cirrus workflows. It
consumes messages from the process SQS queue, extracts a Cirrus Payload from
each message, records the payload in the state database, and starts a Step
Functions execution of the workflow named in the payload's process
definition.

## Trigger

The process SQS queue is the function's event source. Anything that can put a
message on that queue can trigger processing:

- a [feeder](../feeders/index.md) publishing payloads to the queue (directly
  or via the process SNS topic)
- the Cirrus CLI `process` command, which enqueues a payload read from stdin:

        cirrus manage DEPLOYMENT_NAME process < payload.json

A single message carries a single payload; bulk processing is a matter of
sending many messages, which the function consumes in SQS batches.

## Payload extraction

Each message may contain a Cirrus Payload directly, an SNS notification
wrapping a payload, or an object with a `url` field pointing to a payload in
S3, in which case the payload is fetched from S3. Messages from which no
payload can be extracted, or whose payload is not a valid process payload,
are recorded as workflow events (`RECORD_EXTRACT_FAILED` or
`NOT_A_PROCESS_PAYLOAD`), their content is uploaded to the payload bucket for
inspection, and the batch fails so unprocessable messages fall through to the
dead-letter queue.

## State management and workflow start

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
