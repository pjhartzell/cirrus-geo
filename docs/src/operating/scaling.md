# Scaling and quotas

Three settings bound how much work a deployment can run at once: the `process` function's reserved concurrency, which caps how fast executions start; the process queue, which orders what starts next; and, for workflows with Batch tasks, the compute environment's vCPU ceiling. Beyond those, the limits are AWS account quotas. [Earth Search](https://www.element84.com/earth-search/) has processed collections of millions of items through Cirrus; at those volumes the practical ceiling was AWS account quotas, not the framework.

## Process Lambda concurrency

`ProcessLambda` in `cloudformation/core/functions.yaml` sets `ReservedConcurrentExecutions: 16`. Each invocation claims and starts executions for one SQS batch of up to ten messages (`BatchSize: 10` on `ProcessLambdaEventSourceMapping`), so this reservation caps how many executions can be started concurrently. It does not limit how many Step Functions executions run once started.

Raise it by editing `ReservedConcurrentExecutions` and redeploying. Reserved concurrency is subtracted from the account's regional Lambda concurrency pool, so weigh it against everything else running in the account.

## Process queue priority

`core/base.yaml` creates one process queue. The event source mapping consumes it in arrival order under the shared 16-way concurrency, so a large backfill can queue thousands of payloads ahead of newly arriving ones and delay them.

One remedy is a second queue for bulk work. Define it with its own dead-letter queue, mirroring `ProcessQueue` and `ProcessDeadLetterQueue`, and add a second event source mapping on `process` with `ScalingConfig.MaximumConcurrency` set on both mappings so that together they stay within the reservation:

```yaml
# Illustrative. Extends the in-repo core/functions.yaml with a second queue.
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

The in-repo mapping sets no `ScalingConfig`, so today it draws on the full reservation. No Cirrus code reads a bulk-queue variable: `CIRRUS_PROCESS_QUEUE_URL` stays the single queue that `update-state` chains into and that `cirrus manage ... process` submits to. Routing to the bulk queue is the producer's choice. Point backfill [feeders](../building-pipelines/feeders.md) at its URL directly. `process` handles messages from either queue identically.

## Batch compute environments

A workflow with Batch tasks is bounded by its compute environment rather than by Lambda concurrency. `MaxvCpus` is the ceiling on vCPUs allocated across in-flight jobs, and therefore on concurrent jobs, and `MinvCpus` keeps capacity warm between bursts at the cost of paying for it while idle. See [Compute environment](../building-pipelines/batch-infrastructure.md#compute-environment).

## AWS service quotas and limits

Quotas are adjustable through a service quota increase request. Limits are not. The values below are AWS defaults at the time of writing; check the linked AWS pages before relying on them.

### Quotas

- **Lambda concurrent executions** is a regional pool shared by every function in the account. Reserving 16 for `process` removes 16 from that pool. Size the account quota for the deployment's expected parallel volume. See [AWS Lambda quotas](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html).
- **Step Functions open executions** is 1,000,000 per account per region for Standard workflows, which Cirrus state machines are. If item volume approaches this, throttle ingress at the feeder rather than raising the quota. See [Step Functions service quotas](https://docs.aws.amazon.com/step-functions/latest/dg/service-quotas.html).
- **Step Functions API throttling** applies per account per region with a token bucket per action. `StartExecution`, called by `process`, and `GetExecutionHistory`, called by `get-execution-events`, are both adjustable. See the same page.
- **EC2 Spot vCPUs** are quota-limited per instance family, with low defaults that grow with usage. Request an increase before a large Batch run on Spot. See [Amazon EC2 service quotas](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-resource-limits.html).
- **S3 general purpose buckets** default to 10,000 per account, adjustable to 1,000,000. See [Amazon S3 quotas](https://docs.aws.amazon.com/AmazonS3/latest/userguide/BucketRestrictions.html).

### Limits

- **Lambda execution timeout** is 15 minutes and cannot be raised. Longer processing runs as a Batch task. See [Lambda vs Batch](../building-pipelines/tasks.md#lambda-vs-batch).
- **Batch `SubmitJob` and `DescribeJobs`** are limited to 50 requests per second per account per region. A burst of Batch submissions needs a `Retry` on `Batch.AWSBatchException`, as shown in [Batch tasks in a workflow](../building-pipelines/batch-workflow-structure.md#error-handling). See [AWS Batch service quotas](https://docs.aws.amazon.com/batch/latest/userguide/service_limits.html).
