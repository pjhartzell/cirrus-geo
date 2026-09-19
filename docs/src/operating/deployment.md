# Deployment

Cirrus deploys to AWS as a set of nested CloudFormation stacks from the templates in [`cloudformation/`](https://github.com/cirrus-geo/cirrus-geo/tree/main/cloudformation). This page is the reference for what those templates create and accept. For the deploy commands themselves, see the [Quickstart](../getting-started/quickstart.md). For concurrency, quotas, and queue sizing, see [Scaling and quotas](scaling.md).

## Stack layout

`cloudformation/main.yaml` creates six nested stacks:

| Nested stack | Template | Creates |
| --- | --- | --- |
| Base | `core/base.yaml` | Data and payload S3 buckets, the DynamoDB state table, the process SQS queue with its dead-letter queue, a second dead-letter queue for `update-state`, and the publish and workflow-event SNS topics |
| VPC, optional | `core/vpc.yaml` | A VPC with one public and one private subnet, an internet gateway, a NAT gateway, and S3 and DynamoDB gateway endpoints |
| Metrics, optional | `core/metrics.yaml` | The workflow-event log group and its two metric filters. See [Workflow events](../reference/workflow-events.md#cloudwatch-log-group-and-metrics) |
| Functions | `core/functions.yaml` | The five [Lambda functions](../reference/lambda-functions.md) with their IAM roles, the SQS event source mapping for `process`, the EventBridge rule that invokes `update-state`, and a security group when the VPC is enabled |
| API | `core/api.yaml` | An edge-optimized REST API Gateway proxying `GET` requests to the `api` function, deployed to a stage named `dev`, with access logging |
| CLI | `cli/ssm_parameters.yaml` | The Parameter Store entries the Cirrus CLI reads to discover a deployment. See [Deployment discovery](../cli/using-the-cli.md#deployment-discovery) |

A separate bootstrap stack, `bootstrap/bootstrap.yaml`, creates the bucket `${ResourcePrefix}-deployment-artifacts-<account-id>` that `aws cloudformation package` uploads Lambda code and nested templates to. It is deployed before the main stack and is not nested under it.

Resource names derive from `ResourcePrefix`. The buckets are `${ResourcePrefix}-data-<account-id>` and `${ResourcePrefix}-payload-<account-id>`, the state table is `${ResourcePrefix}-state`, the queues are `${ResourcePrefix}-process`, `${ResourcePrefix}-process-dlq`, and `${ResourcePrefix}-update-state-dlq`, the topics are `${ResourcePrefix}-publish` and `${ResourcePrefix}-workflow-event`, and each Lambda function is `${ResourcePrefix}-<name>`.

## Main stack parameters

| Parameter | Default | Description |
| --- | --- | --- |
| `ResourcePrefix` | `cirrus-sandbox` | Prefix for every resource name. 2 to 22 characters, starting with a letter, alphanumeric and hyphens only |
| `LambdaPythonVersion` | none, required | Python runtime version for the Lambda functions, for example `3.13` |
| `LambdaArch` | none, required | CPU architecture for the Lambda functions, `arm64` or `x86_64` |
| `LogLevel` | `DEBUG` | Value of `CIRRUS_LOG_LEVEL` on every function. One of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `EnableVpc` | `true` | Create the VPC stack and attach the Lambda functions to its private subnet |
| `VpcCidr` | `10.1.0.0/16` | VPC CIDR block. Must be a `/16` inside `10.0.0.0/8` |
| `PrivateSubnetCidr` | `10.1.10.0/24` | Private subnet CIDR block |
| `PublicSubnetCidr` | `10.1.1.0/24` | Public subnet CIDR block |
| `EnableWorkflowMetrics` | `true` | Create the metrics stack and enable event logging on `process` and `update-state` |
| `PayloadRootPrefix` | `cirrus` | Root key prefix for every object Cirrus writes to the payload bucket. See [Payload bucket](../reference/payload-bucket.md) |

`EnableVpc` and `EnableWorkflowMetrics` gate the `CreateVpc` and `CreateWorkflowMetrics` conditions in `main.yaml`, which decide whether the corresponding nested stack exists at all.

## Workflow stacks

Each workflow is its own CloudFormation stack, deployed separately from the main stack so it can change without touching core infrastructure. The only coupling is the state machine name, which must be `${ResourcePrefix}-<workflow>` for `process` to find it and for `update-state` to be invoked when it finishes. See [Naming and dispatch](../building-pipelines/workflows.md#naming-and-dispatch). The smallest complete example is `cloudformation/workflows/minimal/state_machine.yaml`, which the quickstart deploys.

## VPC

`core/vpc.yaml` creates a VPC with one public and one private subnet in a single availability zone, an internet gateway, a NAT gateway with an Elastic IP in the public subnet, and S3 and DynamoDB gateway endpoints on the private route table.

When `EnableVpc` is `true`, the functions stack attaches all five Lambda functions to the private subnet through a security group that allows all inbound traffic from the VPC CIDR and all outbound traffic, and attaches the `AWSLambdaVPCAccessExecutionRole` managed policy to their roles. When it is `false`, no VPC stack is created, the functions run without a `VpcConfig`, the `api`, `update-state`, `pre-batch`, and `post-batch` roles get `AWSLambdaBasicExecutionRole` instead, and the `VpcId`, `PrivateSubnetIds`, `PublicSubnetIds`, and `LambdaSecurityGroupId` stack outputs are omitted. The `process` role carries `AWSLambdaVPCAccessExecutionRole` in both cases.

The NAT gateway and Elastic IP are billed hourly whether or not traffic flows through them, so disable the VPC for sandbox deployments unless a function must reach a resource that is only reachable from inside a VPC. Cirrus's own S3 and DynamoDB traffic uses the gateway endpoints and never crosses the NAT gateway.

## Environment variables

Cirrus code reads all configuration from `CIRRUS_*` environment variables. `core/functions.yaml` sets them on each Lambda function, and `cli/ssm_parameters.yaml` publishes a subset to Parameter Store for the Cirrus CLI.

| Variable | Set on | Read by | Purpose |
| --- | --- | --- | --- |
| `CIRRUS_LOG_LEVEL` | all five functions, SSM | `cirrus.lib.logging` | Log level for the Cirrus loggers. Defaults to `DEBUG` when unset |
| `CIRRUS_DATA_BUCKET` | `api`, `process`, `update-state`, SSM | `api` | Bucket holding the `catalog.json` that the API root endpoint reads |
| `CIRRUS_PAYLOAD_BUCKET` | all five functions, SSM | `PayloadBucket` | Bucket for execution, oversized, batch, and invalid payloads. `PayloadBucket.from_env` raises when unset |
| `CIRRUS_PAYLOAD_ROOT_PREFIX` | all five functions, SSM | `PayloadBucket` | Root key prefix in the payload bucket. Defaults to `cirrus` |
| `CIRRUS_STATE_DB` | `api`, `process`, `update-state`, SSM | `StateDB` | State table name. `StateDB` raises when unset |
| `CIRRUS_WORKFLOW_EVENT_TOPIC_ARN` | `process`, `update-state`, SSM | `WorkflowEventManager` | Topic that workflow events are published to. Unset disables publishing |
| `CIRRUS_WORKFLOW_LOG_GROUP` | `process`, `update-state` | `WorkflowMetricLogger` | Log group that workflow events are written to for metric extraction. Empty when the metrics stack is disabled |
| `CIRRUS_WORKFLOW_METRIC_NAMESPACE` | `api` | `WorkflowMetricReader` | Metrics namespace that `/stats` reads. Empty when the metrics stack is disabled |
| `CIRRUS_BASE_WORKFLOW_ARN` | `process`, SSM | `PayloadManagers` | `arn:aws:states:<region>:<account>:stateMachine:${ResourcePrefix}-`, which the workflow name is appended to |
| `CIRRUS_PUBLISH_TOPIC_ARN` | `update-state`, SSM | `update-state` | Topic that output items are published to. Unset skips publishing |
| `CIRRUS_PROCESS_QUEUE_URL` | `update-state`, SSM | `update-state` | Queue that chained payloads are enqueued to. Unset skips chaining |
| `CIRRUS_PREFIX` | SSM only | Cirrus CLI | `${ResourcePrefix}-`, with the trailing hyphen, used to list and invoke the deployment's Lambda functions |
| `CIRRUS_EVENT_DB_AND_TABLE` | none | `EventDB` | Deprecated Timestream destination. Not set by any template. See [Workflow events](../reference/workflow-events.md#timestream-event-database-deprecated) |

`CIRRUS_CLI_IAM_ARN` is an optional Parameter Store entry that no template creates. See [Assuming a role](../cli/using-the-cli.md#assuming-a-role).

## Required deploy permissions

The main stack creates named IAM roles, so `aws cloudformation deploy` needs `--capabilities CAPABILITY_NAMED_IAM`. The deploying identity needs permission to create S3 buckets, a DynamoDB table, SQS queues, SNS topics, Lambda functions, an EventBridge rule, API Gateway resources, SSM parameters, IAM roles, and, when `EnableVpc` is `true`, VPC networking resources.

## Deleting a deployment

Delete workflow stacks first, then the main stack, then the bootstrap stack. The data, payload, and artifacts buckets must be emptied before their stacks will delete. The quickstart's [Stack cleanup](../getting-started/quickstart.md#stack-cleanup) section has the commands.

## Other deployment approaches

The CloudFormation templates in this repository are the deployment path documented here. Two Terraform alternatives are maintained by Element 84 in their own repositories: the [FilmDrop AWS Terraform modules](https://github.com/Element84/filmdrop-aws-tf-modules) include a Cirrus module within a larger FilmDrop deployment, and [terraform-aws-cirrus-processing](https://github.com/Element84/terraform-aws-cirrus-processing) deploys pipeline components, meaning feeders, Batch compute environments, workflows, and tasks, on top of an existing Cirrus deployment.
