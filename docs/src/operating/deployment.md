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
state machine `${ResourcePrefix}-<workflow-name>`, matching the
`CIRRUS_BASE_WORKFLOW_ARN` prefix (`arn:aws:states:<region>:<account>:stateMachine:${ResourcePrefix}-`)
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
(`<database>|<table>`), and the API Lambda falls back to it when configured.
No template in `cloudformation/` provisions a Timestream database or sets
this variable — it is a legacy code path, not something the current
CloudFormation deploy wires up. Use `EnableWorkflowMetrics` for workflow
event metrics in a CloudFormation deployment.

## AWS service quotas and limits

AWS imposes account-level quotas on how many resources of each type you can
create and how frequently some APIs can be called. Quotas are generally
adjustable via a service quota increase request; limits are not.

!!! note
    The specific numbers below are defaults at time of writing — check the
    linked AWS quotas pages for current values before relying on them,
    especially for a production deployment.

### Quotas

- **Lambda concurrent executions**: defaults to 1,000 per account per
  region, shared across all functions. The Process Lambda has a reserved
  concurrency of 16 (`core/functions.yaml`); size the account-level quota
  for your expected parallel workflow volume. See
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

## Processing queue priority

<!-- TODO(phase-3.11): refine into the "Scaling and throughput" section -->

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
producer's choice: point bulk [feeders](../building-pipelines/feeders.md) (or
bulk rerun scripts) at the `ProcessBulkQueue` URL instead of the default
process queue URL. The process Lambda handles messages from either queue
identically.

## Required deploy permissions

Deploying the main stack requires `CAPABILITY_NAMED_IAM` (it creates named
IAM roles for each Lambda function and for API Gateway logging), plus
permissions to create S3 buckets, DynamoDB tables, SQS queues, SNS topics,
Lambda functions, EventBridge rules, API Gateway resources, SSM parameters,
and (when `EnableVpc` is `true`) VPC/EC2 networking resources. See the
[quickstart prerequisites](../getting-started/quickstart.md#prerequisites) for the deploy
commands themselves.

## Deleting a deployment

See the quickstart's [stack cleanup](../getting-started/quickstart.md#stack-cleanup-aws)
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
