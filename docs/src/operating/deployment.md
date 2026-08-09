# Deployment

Cirrus deploys to AWS as a set of nested CloudFormation stacks. This page
covers the parameter surface and stack layout for the templates in
[`cloudformation/`](https://github.com/cirrus-geo/cirrus-geo/tree/main/cloudformation);
for a runnable, step-by-step deploy see the
[quickstart](../getting-started/quickstart.md), which this page does not repeat.

## Stack layout

The main stack (`cloudformation/main.yaml`) orchestrates six nested stacks:

| Nested stack | Template | Creates |
| --- | --- | --- |
| Base | `core/base.yaml` | S3 data and payload buckets, the DynamoDB state table, the SQS process and dead-letter queues, the SNS publish and workflow-event topics |
| VPC (optional) | `core/vpc.yaml` | VPC, public/private subnets, internet and NAT gateways, S3/DynamoDB gateway endpoints |
| Metrics (optional) | `core/metrics.yaml` | CloudWatch log group and metric filters for workflow events |
| Functions | `core/functions.yaml` | The five core Lambda functions (API, Process, Update State, Pre-Batch, Post-Batch) and their IAM roles |
| API | `core/api.yaml` | REST API Gateway (EDGE) proxying to the API Lambda, with CloudWatch access logging |
| CLI | `cli/ssm_parameters.yaml` | Parameter Store entries the Cirrus CLI reads to discover a deployment's resources |

A separate bootstrap stack (`bootstrap/bootstrap.yaml`) creates the S3
bucket used to stage packaged Lambda code and templates before the main
stack deploys — it is not nested under `main.yaml`.

## Main stack parameters

`cloudformation/main.yaml` accepts:

| Parameter | Default | Description |
| --- | --- | --- |
| `ResourcePrefix` | `cirrus-sandbox` | Prefix for all resource names. 2-22 characters, must start with a letter, alphanumeric and hyphens only |
| `VpcCidr` | `10.1.0.0/16` | CIDR block for the VPC (only used when `EnableVpc` is `true`) |
| `PrivateSubnetCidr` | `10.1.10.0/24` | CIDR block for the private subnet |
| `PublicSubnetCidr` | `10.1.1.0/24` | CIDR block for the public subnet |
| `LogLevel` | `DEBUG` | Cirrus log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` |
| `LambdaPythonVersion` | none (required) | Python version for the Lambda runtime, e.g. `3.13` |
| `LambdaArch` | none (required) | CPU architecture for Lambda functions, e.g. `arm64` |
| `EnableVpc` | `true` | Whether to create the VPC stack and attach Lambda functions to it |
| `EnableWorkflowMetrics` | `true` | Whether to create the metrics stack (CloudWatch log group and metric filters) |
| `PayloadRootPrefix` | `cirrus` | Root prefix for all objects written to the payload bucket |

`EnableVpc` and `EnableWorkflowMetrics` each gate a `Condition` in
`main.yaml` (`CreateVpc`, `CreateWorkflowMetrics`) that controls whether the
corresponding nested stack is created at all.

## Workflow stacks

Workflow definitions (Step Functions state machines) deploy as their own
CloudFormation stacks, independent of the main stack, so they can be
iterated on without touching core infrastructure. A workflow stack only
needs `ResourcePrefix` to match the main stack's — from there it names its
state machine `${ResourcePrefix}-WORKFLOW_NAME`, matching the
`CIRRUS_BASE_WORKFLOW_ARN` prefix (`arn:aws:states:REGION:ACCOUNT:stateMachine:${ResourcePrefix}-`)
that the Process Lambda and CLI use to start and reference executions. See
`cloudformation/workflows/minimal/state_machine.yaml` for the smallest
complete example, walked through in the quickstart.

## VPC considerations

`core/vpc.yaml` creates a VPC with one public and one private subnet (single
AZ), an internet gateway, a NAT gateway in the public subnet, and S3/DynamoDB
gateway VPC endpoints attached to the private route table. When `EnableVpc`
is `true`, the functions stack attaches all Lambda functions to the private
subnet through a security group that allows all traffic within the VPC CIDR
and all outbound traffic; the `AWSLambdaVPCAccessExecutionRole` managed
policy is attached to their roles instead of
`AWSLambdaBasicExecutionRole`.

When `EnableVpc` is `false`, no VPC stack is created, Lambda functions run
without `VpcConfig`, and the `VpcId`/`PrivateSubnetIds`/`PublicSubnetIds`/
`LambdaSecurityGroupId` stack outputs are omitted. A NAT gateway and Elastic
IP are billed hourly regardless of traffic, so disabling the VPC (as the
LocalStack path in the quickstart does) avoids that cost for sandbox or
local development deployments. Enable it when Lambda functions need to
reach resources that are only network-reachable from inside a VPC (for
example, a private database); the S3 and DynamoDB gateway endpoints mean
Cirrus's own S3/DynamoDB traffic does not need the NAT gateway either way.

## Workflow event metrics

Workflow state-change events are recorded to CloudWatch metrics when
`EnableWorkflowMetrics` is `true`: the metrics stack creates a log group and
two metric filters (`all_workflows_by_event`, `a_workflow_by_event`); the
`process` and `update-state` functions get a `CIRRUS_WORKFLOW_LOG_GROUP`
environment variable to write events to, and the `api` function gets
`CIRRUS_WORKFLOW_METRIC_NAMESPACE` to read the extracted metrics back. This
is what the `api` function's `/stats` endpoint reads by default.

`cirrus.lib.eventdb.EventDB` also supports recording events to a Timestream
database via a `CIRRUS_EVENT_DB_AND_TABLE` environment variable
(`DATABASE\|TABLE`), and the API Lambda falls back to it when configured.
No template in `cloudformation/` provisions a Timestream database or sets
this variable — it is a legacy code path, not something the current
CloudFormation deploy wires up. Use `EnableWorkflowMetrics` for workflow
event metrics in a CloudFormation deployment.

## Environment variables

Cirrus code reads its configuration entirely from `CIRRUS_*` environment
variables — no config file. `core/functions.yaml` sets them on each Lambda
function from stack parameters and outputs; `cli/ssm_parameters.yaml`
publishes the deployment-scoped subset to Parameter Store for the Cirrus CLI
to read at run time (see [deployment discovery](../cli/using-the-cli.md#deployment-discovery)).

| Variable | Set on (Lambda) | Read by | Purpose |
| --- | --- | --- | --- |
| `CIRRUS_LOG_LEVEL` | api, process, update-state, pre-batch, post-batch | `cirrus.lib.logging` | Log level for the Cirrus logging config; defaults to `DEBUG` if unset. Set from the `LogLevel` stack parameter. |
| `CIRRUS_DATA_BUCKET` | api, process, update-state | `api.py` | S3 bucket holding the STAC catalog the `api` function's root endpoint reads (`catalog.json`). Set from `CirrusDataBucket`. |
| `CIRRUS_PAYLOAD_BUCKET` | api, process, update-state, pre-batch, post-batch | `cirrus.lib.payload_bucket.PayloadBucket` | S3 bucket for execution, oversized, batch, and invalid payloads (see [Payload Bucket](../reference/payload-bucket.md)). Set from `CirrusPayloadBucket`; required — `PayloadBucket` raises if unset. |
| `CIRRUS_PAYLOAD_ROOT_PREFIX` | api, process, update-state, pre-batch, post-batch | `cirrus.lib.payload_bucket.PayloadBucket` | Root key prefix under which payload bucket objects are organized; defaults to `cirrus`. Set from the `PayloadRootPrefix` stack parameter. |
| `CIRRUS_STATE_DB` | api, process, update-state | `cirrus.lib.statedb.StateDB` | DynamoDB state table name. Set from `StateTable`; required — `StateDB` raises if unset. |
| `CIRRUS_WORKFLOW_EVENT_TOPIC_ARN` | process, update-state | `cirrus.lib.events` | SNS topic ARN workflow state-change events are published to. Set from `WorkflowEventTopicArn`. |
| `CIRRUS_WORKFLOW_LOG_GROUP` | process, update-state | `cirrus.lib.events` | CloudWatch log group workflow events are written to for metric extraction; empty string disables it. Set from `WorkflowMetricLogGroup` (only non-empty when `EnableWorkflowMetrics` is `true`). |
| `CIRRUS_WORKFLOW_METRIC_NAMESPACE` | api | `cirrus.lib.events.WorkflowMetricReader` | CloudWatch metrics namespace the `api` function's `/stats` endpoint reads from; empty string disables metric reads. Set from `WorkflowMetricNamespace` (only non-empty when `EnableWorkflowMetrics` is `true`). |
| `CIRRUS_BASE_WORKFLOW_ARN` | process | `cirrus.lib.payload_manager` | Base Step Functions state machine ARN prefix (`arn:aws:states:REGION:ACCOUNT:stateMachine:RESOURCE_PREFIX-`) used to build execution ARNs. Set from a `!Sub` expression in `core/functions.yaml`, not a passed-through parameter. |
| `CIRRUS_PUBLISH_TOPIC_ARN` | update-state | `update_state.py` | SNS topic ARN output items are published to on successful completion; unset means publishing is skipped. Set from `PublishTopicArn`. |
| `CIRRUS_PROCESS_QUEUE_URL` | update-state | `update_state.py` | Process SQS queue URL chained payloads are enqueued to; unset means chaining is skipped. Set from `ProcessQueueUrl`. |
| `CIRRUS_EVENT_DB_AND_TABLE` | none | `cirrus.lib.eventdb.EventDB` | `DATABASE\|TABLE` pair for the Timestream event-recording fallback. No template sets this — see [above](#workflow-event-metrics). |
| `CIRRUS_PREFIX` | none (SSM only) | `cirrus.management.deployment` | Prefix used by the Cirrus CLI to identify a deployment's Lambda functions and build workflow ARNs. Published to Parameter Store from `ResourcePrefix` by `cli/ssm_parameters.yaml`; not a Lambda environment variable. |

`CIRRUS_CLI_IAM_ARN` is a CLI-only, optional SSM parameter (not set by any
template) covered in [Assuming a role](../cli/using-the-cli.md#assuming-a-role-cirrus_cli_iam_arn).

## AWS service quotas and limits

AWS imposes account-level quotas on how many resources of each type you can
create and how frequently some APIs can be called. Quotas are generally
adjustable via a service quota increase request; limits are not.

!!! note
    The specific numbers below are defaults at time of writing — check the
    linked AWS quotas pages for current values before relying on them,
    especially for a production deployment.

### Quotas

- **Lambda concurrent executions**: an account-per-region quota shared
  across all functions; reserving concurrency for one function (as the
  process Lambda does — see [Scaling and throughput](#scaling-and-throughput))
  reduces what is available to the rest. Size the account-level quota for
  the deployment's expected parallel workflow volume. See
  [AWS Lambda quotas](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html).
- **Step Functions open executions**: 1,000,000 open executions per account
  per region for Standard workflows (Cirrus workflow state machines are
  Standard). If a higher item volume needs processing, throttle ingress
  earlier in the pipeline rather than raising this quota. See
  [Step Functions service quotas](https://docs.aws.amazon.com/step-functions/latest/dg/service-quotas.html).
- **Step Functions API throttling**: `StartExecution` and
  `GetExecutionHistory` (used by the Process Lambda and by `cirrus manage
  run-workflow` respectively) are throttled per account per region via a
  token-bucket scheme with separate bucket size and refill rate; both can be
  increased. See
  [Step Functions service quotas](https://docs.aws.amazon.com/step-functions/latest/dg/service-quotas.html)
  for current values.
- **EC2 Spot vCPUs**: AWS Batch compute environments backed by Spot
  Instances (used by the batch-processing path) draw from a per-account,
  per-instance-family vCPU quota that defaults low for most families and
  autoscales with usage; request an increase before running large Batch
  jobs. See
  [Amazon EC2 service quotas](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-resource-limits.html).
- **S3 general purpose buckets**: 10,000 per account by default, adjustable
  up to 1,000,000. See
  [Amazon S3 quotas](https://docs.aws.amazon.com/AmazonS3/latest/userguide/BucketRestrictions.html).

### Limits

- **Lambda execution timeout**: 15 minutes, a hard ceiling that cannot be
  increased — this is why long-running processing goes through AWS Batch
  rather than a Lambda function.
- **Batch `SubmitJob`/`DescribeJobs`**: 50 requests/second per account per
  region, a fixed limit (not adjustable). Design retry/backoff around this
  if submitting many Batch jobs in a burst. See
  [AWS Batch service quotas](https://docs.aws.amazon.com/batch/latest/userguide/service_limits.html).

## Scaling and throughput

Three independent points determine how much processing volume a deployment
can push through concurrently: the process Lambda's reserved concurrency,
the process queue's structure, and the AWS Batch compute environment sizing
for workflows that use Batch tasks.

### Process Lambda concurrency

`ProcessLambda` in `core/functions.yaml` sets `ReservedConcurrentExecutions:
16`, capping the process Lambda at 16 concurrent invocations regardless of
the account-level Lambda concurrency quota. Since each invocation claims and
starts workflow executions for one SQS batch (up to `BatchSize: 10` payloads,
set on `ProcessLambdaEventSourceMapping`), this reserved concurrency is the
practical ceiling on how many workflow executions can be *started*
concurrently — it does not limit how many Step Functions executions can run
once started. Raise it by editing `ReservedConcurrentExecutions` in
`core/functions.yaml` and redeploying the functions stack; reserving more
concurrency for one function reduces the pool available to the rest of the
account, so weigh it against the account's overall Lambda concurrency quota
(see [AWS Lambda quotas](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html)).

### Process queue priority

By default, `core/base.yaml` creates a single `ProcessQueue`. Because the
process Lambda's event source mapping (`ProcessLambdaEventSourceMapping`)
consumes it in arrival order and shares the same 16-way reserved
concurrency, thousands of older, lower-priority payloads (a backfill or a
bulk re-run) can queue ahead of newly generated, higher-priority payloads
and delay them.

Splitting into a priority and a bulk queue addresses this: define a second
queue (with its own dead-letter queue, mirroring `ProcessQueue` and
`ProcessDeadLetterQueue`) and give the process Lambda a second event source
mapping pointed at it, each with a `ScalingConfig.MaximumConcurrency` to
divide the Lambda's 16-way concurrency between the two queues:

```yaml
# Illustrative — extends the in-repo core/functions.yaml with a second queue.
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

`ScalingConfig.MaximumConcurrency` is not set on the in-repo
`ProcessLambdaEventSourceMapping`, so it currently draws from the full
reserved concurrency; adding a second mapping means capping both explicitly,
since the two together should not exceed the 16-way reservation above.

No Cirrus code reads a bulk-queue environment variable — `CIRRUS_PROCESS_QUEUE_URL`
remains the single queue used by workflow chaining (`update-state`) and
`cirrus manage ... process`. Routing to a bulk queue is the producer's
choice: point bulk [feeders](../building-pipelines/feeders.md) or backfill
scripts at the bulk queue's URL directly. The process Lambda handles
messages from either queue identically.

### Batch-backed workflows

Workflows with Batch tasks are bound by the Batch compute environment
instead of Lambda concurrency. `MinvCpus`/`MaxvCpus` on the compute
environment set the idle floor and the concurrent-job ceiling; see
[Compute environment](../building-pipelines/batch-infrastructure.md#compute-environment)
for how those interact with instance allocation and `AllocationStrategy`.

## Required deploy permissions

Deploying the main stack requires `CAPABILITY_NAMED_IAM` (it creates named
IAM roles for each Lambda function and for API Gateway logging), plus
permissions to create S3 buckets, DynamoDB tables, SQS queues, SNS topics,
Lambda functions, EventBridge rules, API Gateway resources, SSM parameters,
and (when `EnableVpc` is `true`) VPC/EC2 networking resources. See the
[quickstart prerequisites](../getting-started/quickstart.md#prerequisites) for the deploy
commands themselves.

## Deleting a deployment

See the quickstart's [stack cleanup](../getting-started/quickstart.md#stack-cleanup)
section for the emptying and delete-order steps (workflow stacks, then the
main stack, then bootstrap).

## Other deployment approaches

The CloudFormation templates in this repository are the deployment path
maintained and documented here. Two external Terraform-based alternatives
exist: the [FilmDrop AWS Terraform modules](https://github.com/Element84/filmdrop-aws-tf-modules)
include a Cirrus module as part of a broader FilmDrop deployment, and
[terraform-aws-cirrus-processing](https://github.com/Element84/terraform-aws-cirrus-processing)
is a standalone Terraform module for Cirrus processing infrastructure. Their
interfaces are documented in their own repositories.
