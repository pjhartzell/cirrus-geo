# Functions

The `function` component type refers to the AWS Lambda functions built into
Cirrus. These functions wrap the workflows and tasks: they move payloads into
and out of workflows, track state, and expose deployment data over HTTP. All
five are created by the CloudFormation core stack.

- [`process`](process.md): consumes payloads from the process SQS queue,
  records them in the state database, and starts workflow Step Functions
  executions.
- [`update-state`](update-state.md): handles Step Functions execution
  completion events, updating the state database, publishing notifications,
  and enqueuing chained payloads.
- [`pre-batch`](pre_batch.md): runs before a Batch task in a workflow,
  uploading the input payload to S3 and returning its URL for the Batch job.
- [`post-batch`](post_batch.md): runs after a Batch task in a workflow,
  retrieving the task output payload from S3; on job failure it retrieves the
  error from the Batch job logs and re-raises it in the Step Functions
  context.
- [`api`](api.md): a read-only HTTP API for querying workflow state and event
  metrics, e.g., for monitoring dashboards.
