# Tips and Tricks

## Processing Queue Priority

By default, there is only one `process` queue. This can cause difficulty when
doing back-processing or failure re-runs, as thousands of older,
lower-priority payloads can pile up in front of newly-generated,
higher-priority payloads. A solution is to create an additional "bulk" queue
and put the lower-priority payloads into it.

Alongside the existing `ProcessQueue` and `ProcessDeadLetterQueue` resources
(`cloudformation/core/base.yaml`), define a `ProcessBulkQueue` and associated
dead-letter queue with the same settings. Then give the process Lambda a
second event source mapping, using each mapping's
`ScalingConfig.MaximumConcurrency` to divide the Lambda's concurrency between
the queues — the in-repo mapping is `ProcessLambdaEventSourceMapping` in
`cloudformation/core/functions.yaml`:

```yaml
# Illustrative — extends the in-repo templates with a second queue.
ProcessLambdaEventSourceMapping:
  Type: AWS::Lambda::EventSourceMapping
  Properties:
    EventSourceArn: !Ref ProcessQueueArn
    FunctionName: !Ref ProcessLambda
    BatchSize: 10
    ScalingConfig:
      MaximumConcurrency: 12

ProcessLambdaBulkEventSourceMapping:
  Type: AWS::Lambda::EventSourceMapping
  Properties:
    EventSourceArn: !GetAtt ProcessBulkQueue.Arn
    FunctionName: !Ref ProcessLambda
    BatchSize: 10
    ScalingConfig:
      MaximumConcurrency: 4
```

No Cirrus code reads a bulk-queue environment variable —
`CIRRUS_PROCESS_QUEUE_URL` remains the default queue used by workflow
chaining and `cirrus manage ... process`. Routing to the bulk queue is the
producer's choice: point bulk [feeders](../components/feeders/index.md) (or
bulk rerun scripts) at the `ProcessBulkQueue` URL instead of the default
process queue URL. The process Lambda handles messages from either queue
identically.
