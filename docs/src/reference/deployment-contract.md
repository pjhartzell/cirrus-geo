# Deployment contract

A Cirrus deployment is a set of AWS resources plus the configuration that connects them. This page states that set as requirements: what must exist, what it must be named, and what each function must be told. The CloudFormation templates in [`cloudformation/`](https://github.com/cirrus-geo/cirrus-geo/tree/main/cloudformation) satisfy every requirement here and are the source for each statement. A deployment built with other tooling, such as the [Terraform modules](#other-tooling) listed at the end, has to satisfy them the same way.

Procedures for the reference templates are on [Deploying to AWS](../operating/deploying.md).

## Resources

The main stack, `cloudformation/main.yaml`, creates six nested stacks. A separate bootstrap stack, `bootstrap/bootstrap.yaml`, creates the artifacts bucket that `aws cloudformation package` uploads code and templates to before the main stack exists.

| Nested stack | Template | Creates |
| --- | --- | --- |
| Base | `core/base.yaml` | Data and payload S3 buckets, the DynamoDB state table, the process SQS queue with its dead-letter queue, a second dead-letter queue for `update-state`, and the publish and workflow-event SNS topics |
| VPC, optional | `core/vpc.yaml` | A VPC with one public and one private subnet, an internet gateway, a NAT gateway, and S3 and DynamoDB gateway endpoints |
| Metrics, optional | `core/metrics.yaml` | The workflow-event log group and its two metric filters. See [Workflow events](workflow-events.md#cloudwatch-log-group-and-metrics) |
| Functions | `core/functions.yaml` | The five [Lambda functions](lambda-functions.md) with their IAM roles, the SQS event source mapping for `process`, the EventBridge rule that invokes `update-state`, and a security group when the VPC is enabled |
| API | `core/api.yaml` | An edge-optimized REST API Gateway proxying `GET` requests to the `api` function, deployed to a stage named `dev`, with access logging |
| CLI | `cli/ssm_parameters.yaml` | The Parameter Store entries the Cirrus CLI reads. See [Parameter Store entries](#parameter-store-entries) |

Only the base and functions stacks are required for payloads to flow. The API stack serves the read-only [HTTP API](http-api.md), the CLI stack makes the deployment visible to the Cirrus CLI, and the VPC and metrics stacks are optional in the templates themselves.

### Names

Every name derives from one prefix, `ResourcePrefix` in the templates. Two of them are load-bearing: the state machine name prefix is how `process` finds a workflow and how the EventBridge rule recognizes one, and the Lambda function prefix is how the CLI lists a deployment's functions.

| Resource | Name |
| --- | --- |
| Data bucket | `${ResourcePrefix}-data-<account-id>` |
| Payload bucket | `${ResourcePrefix}-payload-<account-id>` |
| Artifacts bucket | `${ResourcePrefix}-deployment-artifacts-<account-id>` |
| State table | `${ResourcePrefix}-state` |
| Process queue and its dead-letter queue | `${ResourcePrefix}-process`, `${ResourcePrefix}-process-dlq` |
| `update-state` dead-letter queue | `${ResourcePrefix}-update-state-dlq` |
| Publish and workflow-event topics | `${ResourcePrefix}-publish`, `${ResourcePrefix}-workflow-event` |
| Lambda functions | `${ResourcePrefix}-api`, `-process`, `-update-state`, `-pre-batch`, `-post-batch` |
| Workflow state machines | `${ResourcePrefix}-<workflow>`, one per workflow, in their own stacks |
| Metrics log group and namespace | `${ResourcePrefix}-workflow-event-metrics`, `${ResourcePrefix}-workflow` |

The prefix is 2 to 22 characters, starts with a letter, and contains only letters, digits, and hyphens.

### Resource properties the code depends on

- **State table** keys: partition key `collections_workflow`, sort key `itemids`, both strings, with two global secondary indexes named `state_updated` and `updated` that share the partition key and sort on the attribute of the same name, projecting all attributes. See [State database: Key schema](state-database.md#key-schema).
- **Process queue**: `process` is its only consumer, through an event source mapping with a batch size of 10. The templates set a visibility timeout of 180 seconds and redrive to the dead-letter queue after 5 receives.
- **Payload bucket**: a lifecycle rule expiring `<PayloadRootPrefix>/tmp/` after 10 days. See [Payload bucket: Lifecycle and retention](payload-bucket.md#lifecycle-and-retention).
- **EventBridge rule**: matches `detail-type` `Step Functions Execution Status Change` from source `aws.states`, with `detail.stateMachineArn` beginning `arn:aws:states:<region>:<account>:stateMachine:${ResourcePrefix}-` and `detail.status` in `SUCCEEDED`, `FAILED`, `ABORTED`, `TIMED_OUT`. Its target is `update-state`, with the `update-state` dead-letter queue as dead-letter target and a maximum event age of 1800 seconds.
- **Lambda functions**: Python runtime, handlers `api.lambda_handler`, `process.lambda_handler`, `update_state.lambda_handler`, `pre_batch.lambda_handler`, `post_batch.lambda_handler` from the packaged distribution. The templates use a 15-second timeout, 256 MB, and reserve 16 concurrent executions for `process`. See [Scaling and quotas](../operating/scaling.md#process-lambda-concurrency).

## Main stack parameters

| Parameter | Default | Description |
| --- | --- | --- |
| `ResourcePrefix` | `cirrus-sandbox` | Prefix for every resource name |
| `LambdaPythonVersion` | none, required | Python runtime version for the Lambda functions, for example `3.13` |
| `LambdaArch` | none, required | CPU architecture for the Lambda functions, `arm64` or `x86_64` |
| `LogLevel` | `DEBUG` | Value of `CIRRUS_LOG_LEVEL` on every function. One of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `EnableVpc` | `true` | Create the VPC stack and attach the Lambda functions to its private subnet |
| `VpcCidr` | `10.1.0.0/16` | VPC CIDR block. Must be a `/16` inside `10.0.0.0/8` |
| `PrivateSubnetCidr` | `10.1.10.0/24` | Private subnet CIDR block |
| `PublicSubnetCidr` | `10.1.1.0/24` | Public subnet CIDR block |
| `EnableWorkflowMetrics` | `true` | Create the metrics stack and enable event logging on `process` and `update-state` |
| `PayloadRootPrefix` | `cirrus` | Root key prefix for every object Cirrus writes to the payload bucket |

`EnableVpc` and `EnableWorkflowMetrics` gate the `CreateVpc` and `CreateWorkflowMetrics` conditions in `main.yaml`, which decide whether the corresponding nested stack exists at all.

### VPC

`core/vpc.yaml` creates a VPC with one public and one private subnet in a single availability zone, an internet gateway, a NAT gateway with an Elastic IP in the public subnet, and S3 and DynamoDB gateway endpoints on the private route table.

When `EnableVpc` is `true`, the functions stack attaches all five Lambda functions to the private subnet. The security group allows all inbound traffic from the VPC CIDR and all outbound traffic, and each role gets the `AWSLambdaVPCAccessExecutionRole` managed policy.

When it is `false`:

- No VPC stack is created and the functions run without a `VpcConfig`.
- The `api`, `update-state`, `pre-batch`, and `post-batch` roles get `AWSLambdaBasicExecutionRole` instead. The `process` role carries `AWSLambdaVPCAccessExecutionRole` either way.
- The `VpcId`, `PrivateSubnetIds`, `PublicSubnetIds`, and `LambdaSecurityGroupId` stack outputs are omitted.

The NAT gateway and Elastic IP are billed hourly whether or not traffic flows through them. Cirrus's own S3 and DynamoDB traffic uses the gateway endpoints and never crosses the NAT gateway, so the VPC is only needed when a function must reach a resource that is reachable only from inside one.

## Environment variables

Cirrus code reads all configuration from `CIRRUS_*` environment variables. There is no configuration file. The table gives what each function must be given.

| Variable | Required on | Read by | Purpose |
| --- | --- | --- | --- |
| `CIRRUS_LOG_LEVEL` | all five, optional | `cirrus.lib.logging` | Log level for the Cirrus loggers. Defaults to `DEBUG` when unset |
| `CIRRUS_DATA_BUCKET` | `api` | `api` | Bucket holding the `catalog.json` that the API root endpoint reads. The templates also set it on `process` and `update-state`, which do not read it |
| `CIRRUS_PAYLOAD_BUCKET` | all five | `PayloadBucket` | Bucket for execution, oversized, batch, and invalid payloads. `PayloadBucket.from_env` raises when unset |
| `CIRRUS_PAYLOAD_ROOT_PREFIX` | all five, optional | `PayloadBucket` | Root key prefix in the payload bucket. Defaults to `cirrus` |
| `CIRRUS_STATE_DB` | `api`, `process`, `update-state` | `StateDB` | State table name. `StateDB` raises when unset |
| `CIRRUS_BASE_WORKFLOW_ARN` | `process` | `PayloadManagers` | `arn:aws:states:<region>:<account>:stateMachine:${ResourcePrefix}-`, which the workflow name is appended to |
| `CIRRUS_WORKFLOW_EVENT_TOPIC_ARN` | `process`, `update-state`, optional | `WorkflowEventManager` | Topic that workflow events are published to. Unset disables publishing |
| `CIRRUS_WORKFLOW_LOG_GROUP` | `process`, `update-state`, optional | `WorkflowMetricLogger` | Log group that workflow events are written to for metric extraction. Empty or unset disables it |
| `CIRRUS_WORKFLOW_METRIC_NAMESPACE` | `api`, optional | `WorkflowMetricReader` | Metrics namespace that `/stats` reads. Empty or unset disables it |
| `CIRRUS_PUBLISH_TOPIC_ARN` | `update-state`, optional | `update-state` | Topic that output items are published to. Unset skips publishing |
| `CIRRUS_PROCESS_QUEUE_URL` | `update-state`, optional | `update-state` | Queue that chained payloads are enqueued to. Unset skips chaining |
| `CIRRUS_EVENT_DB_AND_TABLE` | none | `EventDB` | Deprecated Timestream destination. Not set by any template. See [Workflow events](workflow-events.md#timestream-event-database-deprecated) |

## IAM grants

Each function has its own role in `core/functions.yaml`. These are the grants the code exercises.

| Function | Grants |
| --- | --- |
| `process` | `s3:GetObject`, `ListBucket`, `GetBucketLocation` on any bucket; `s3:PutObject` on the payload bucket; read and write on the state table and its indexes; `sqs:ReceiveMessage`, `DeleteMessage`, `GetQueueUrl`, `GetQueueAttributes` on the process queue; `sns:Publish` on the workflow event topic; `states:StartExecution` on `stateMachine:${ResourcePrefix}-*`; `logs:CreateLogStream`, `PutLogEvents`, `DescribeLogGroups`, `DescribeLogStreams` on the metrics log group when enabled |
| `update-state` | Read and write on the state table; `sqs:SendMessage` on the process queue; `s3:GetObject` and `PutObject` on the payload bucket; `sns:Publish` on the publish and workflow event topics; the same log grants as `process` |
| `pre-batch` | `s3:GetObject`, `ListBucket`, `GetBucketLocation` on any bucket; `s3:PutObject` on the payload bucket |
| `post-batch` | The same S3 grants as `pre-batch`; `logs:GetLogEvents` on `/aws/batch/*` |
| `api` | `s3:ListBucket`, `GetObject`, `GetBucketLocation` on the data bucket; `dynamodb:Query`, `Scan`, `GetItem`, `DescribeTable` on the state table and its indexes; `cloudwatch:GetMetricData`, `GetMetricStatistics`, `ListMetrics` when the metrics namespace is set |

`process` and the Batch functions read from any bucket because a payload may arrive as a `{"url": ...}` reference to an object stored elsewhere. Each workflow's state machine role is the workflow author's; it must be allowed to invoke the workflow's Lambda functions and, for Batch tasks, `batch:SubmitJob` plus the EventBridge permissions that `submitJob.sync` needs.

## Parameter Store entries

The Cirrus CLI discovers a deployment through AWS Systems Manager Parameter Store. It reads a pointer at `/cirrus/deployments/<name>` whose value is `{"type": "parameter_store", "value": "/deployment/<name>/"}`, then every parameter under that path. `cli/ssm_parameters.yaml` creates them with `<name>` equal to `ResourcePrefix`.

| Parameter under `/deployment/<name>/` | Required by the CLI | Value |
| --- | --- | --- |
| `CIRRUS_PAYLOAD_BUCKET` | yes | Payload bucket name |
| `CIRRUS_STATE_DB` | yes | State table name |
| `CIRRUS_PROCESS_QUEUE_URL` | yes | Process queue URL |
| `CIRRUS_BASE_WORKFLOW_ARN` | yes | The state machine ARN prefix, as on the functions |
| `CIRRUS_PREFIX` | yes | `${ResourcePrefix}-`, with the trailing hyphen, used to list and invoke the deployment's Lambda functions |
| `CIRRUS_DATA_BUCKET`, `CIRRUS_PUBLISH_TOPIC_ARN`, `CIRRUS_WORKFLOW_EVENT_TOPIC_ARN`, `CIRRUS_PAYLOAD_ROOT_PREFIX`, `CIRRUS_LOG_LEVEL` | no | Same values as on the functions, loaded into the environment by `exec`, `call`, and `template-payload` |
| `CIRRUS_CLI_IAM_ARN` | no | A role for the CLI to assume. Not created by any template. See [Assuming a role](../cli/using-the-cli.md#assuming-a-role) |

The CLI fails with a message naming the missing entries if any required one is absent.

## Other tooling

Two Terraform alternatives to the CloudFormation templates are maintained by Element 84 in their own repositories. The [FilmDrop AWS Terraform modules](https://github.com/Element84/filmdrop-aws-tf-modules) include a Cirrus module within a larger FilmDrop deployment. [terraform-aws-cirrus-processing](https://github.com/Element84/terraform-aws-cirrus-processing) deploys pipeline components, meaning feeders, Batch compute environments, workflows, and tasks, on top of an existing Cirrus deployment.
