# Workflows

A workflow models the transformation of an input payload into one or more
output items via processing through one or more tasks. Workflows are
implemented as [AWS Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html)
state machines, written in the [AWS States Language](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-amazon-states-language.html).

A workflow definition is a CloudFormation template that deploys a
`AWS::StepFunctions::StateMachine` resource, along with the IAM role the
state machine assumes to invoke its tasks. See
[Writing workflow definitions](#writing-workflow-definitions) for the required structure and
naming, and the in-repo `minimal` workflow
(`cloudformation/workflows/minimal/state_machine.yaml`) for a working
example.

The `process` Lambda function dispatches each incoming payload to the Step
Functions execution named in the payload's `process` definition. When an
execution reaches a terminal status, the `update-state` Lambda function
records the result in the [state database](../../cirrus/70_statedb.md) and
handles [chaining](chaining.md) to any subsequent workflow.

## Writing workflow definitions

Cirrus workflows are implemented via [AWS Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html)
and written in the [AWS States Language](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-amazon-states-language.html).
A workflow is deployed as a CloudFormation template defining an
`AWS::StepFunctions::StateMachine` resource and the IAM role it assumes.

### Minimal example

The in-repo `minimal` workflow (`cloudformation/workflows/minimal/state_machine.yaml`)
is the simplest complete example: a `Choice` state that succeeds or fails
depending on a field in the input payload.

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: 'Cirrus - Minimal Workflow Step Function'

Parameters:
  ResourcePrefix:
    Type: String
    Description: Prefix for all resource names

Resources:
  MinimalWorkflowStateMachine:
    Type: AWS::StepFunctions::StateMachine
    Properties:
      StateMachineName: !Sub '${ResourcePrefix}-minimal'
      RoleArn: !GetAtt StateMachineRole.Arn
      DefinitionString: |
        {
          "Comment": "Minimal workflow for testing",
          "StartAt": "CheckWorkflow",
          "States": {
            "CheckWorkflow": {
              "Type": "Choice",
              "Choices": [
                {
                  "Variable": "$.process[0].succeed",
                  "BooleanEquals": true,
                  "Next": "Success"
                }
              ],
              "Default": "FailState"
            },
            "Success": {
              "Type": "Succeed"
            },
            "FailState": {
              "Type": "Fail",
              "Error": "WorkflowMismatch",
              "Cause": "The succeed field was not true"
            }
          }
        }

  StateMachineRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: !Sub '${ResourcePrefix}-minimal-workflow-role'
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: states.amazonaws.com
            Action: 'sts:AssumeRole'
      ManagedPolicyArns:
        - 'arn:aws:iam::aws:policy/CloudWatchLogsFullAccess'
```

The `minimal` workflow has no tasks — it only exercises the process/state
machinery, which is why its `Fail` state can use static `Error`/`Cause`
strings. A workflow with real tasks should capture the actual error from a
failed task instead; see [Capturing errors](#capturing-errors) below.

### A workflow with a Lambda task

A workflow that invokes a Lambda function uses the
`arn:aws:states:::lambda:invoke` resource, with the function ARN passed in
`Parameters.FunctionName` rather than as the state's `Resource` directly.
This produces additional metadata in the execution history, including the
Lambda request ID, which can be used to filter the function's CloudWatch
logs (see [Lambda logs](../tasks/index.md#lambda-logs)).

```json
{
    "Comment": "Example workflow with a single Lambda task",
    "StartAt": "my-task",
    "States": {
        "my-task": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {
                "FunctionName": "arn:aws:lambda:us-east-1:123456789012:function:my-prefix-my-task",
                "Payload.$": "$"
            },
            "End": true,
            "Retry": [
                {
                    "ErrorEquals": [
                        "Lambda.TooManyRequestsException",
                        "Lambda.Unknown"
                    ],
                    "IntervalSeconds": 1,
                    "BackoffRate": 2,
                    "MaxAttempts": 5
                }
            ],
            "Catch": [
                {
                    "ErrorEquals": [
                        "States.ALL"
                    ],
                    "ResultPath": "$.error",
                    "Next": "failure"
                }
            ]
        },
        "failure": {
            "Type": "Fail",
            "ErrorPath": "$.error.Error",
            "CausePath": "$.error.Cause"
        }
    }
}
```

The `Payload.$: "$"` parameter passes the full state input (the Cirrus
Payload) to the Lambda function unmodified.

#### Workflow naming

A workflow's state machine is named `${ResourcePrefix}-<workflow_name>`,
where `ResourcePrefix` is the CloudFormation stack's resource prefix
parameter and `<workflow_name>` is the workflow's own name — `minimal` in
the example above.

The `process` Lambda function dispatches incoming payloads to the
corresponding state machine. It reads the workflow name from the payload's
process definition (the `workflow` field) and builds the full state machine
ARN from the `CIRRUS_BASE_WORKFLOW_ARN` environment variable, which is set
to `arn:aws:states:<region>:<account-id>:stateMachine:${ResourcePrefix}-`.
A payload therefore only needs to specify a workflow name (e.g.
`"workflow": "minimal"`); `process` derives the full ARN and starts that
state machine's execution.

For a workflow to be reachable by `process`, its state machine must be named
following this `${ResourcePrefix}-<workflow_name>` convention.

### Basic state machine structure

Workflows share some common structure within the state machine definition:

- A `Comment` describing the workflow.
- `StartAt` set to the first state.
- At least one state that ends the workflow successfully (`End: true` on a
  `Task` state, or a `Succeed` state).
- A `Fail` state that terminates the workflow on unrecoverable error, with
  each task's `Catch` block routing to it.

Review the built-in `minimal` workflow for the smallest working example, and
see [Batch tasks in workflows](batch.md) for the additional structure Batch
tasks require.

### Triggering workflows off one another

It is common to model a processing pipeline as a series of connected
workflows. Cirrus supports this via:

- **Workflow chaining**: a chain of process definitions is specified in the
  payload's `process` array, so that the output of one workflow execution
  becomes the input to the next. See [Workflow chaining](chaining.md).
- **Publish topic subscriptions**: custom Lambda functions or other
  listeners can subscribe to the publish SNS topic to process workflow
  output items and trigger further processing outside of a pre-defined
  chain.

### Error handling

Some errors occur before a task even executes — for example, a
`Lambda.TooManyRequestsException` when the Lambda concurrency quota is
exceeded, or an AWS Batch `AWSBatchException` when the Batch `SubmitJob`
rate quota is breached. These should be retried, but an immediate retry is
likely to fail again if the underlying load hasn't subsided, so each task
needs a retry definition with backoff.

A retry definition with backoff and jitter looks like:

```json
{
    "IntervalSeconds": 600,
    "MaxDelaySeconds": 86400,
    "BackoffRate": 2.0,
    "MaxAttempts": 20,
    "JitterStrategy": "FULL"
}
```

`JitterStrategy: FULL` randomizes each retry delay between 0 and the current
backoff interval, rather than always waiting the full interval
(`JitterStrategy: NONE`, the default). This avoids many failed executions
retrying in lockstep and re-creating the same load spike. `IntervalSeconds`
sets the first delay; each subsequent retry multiplies the prior interval by
`BackoffRate`, up to `MaxAttempts` attempts and capped at `MaxDelaySeconds`.

#### Capturing errors

When a Step Functions task fails, the error information needs to reach the
`update-state` Lambda function so it can be recorded in the state database.
`update-state` reads the execution's error and cause from the EventBridge
"Step Functions Execution Status Change" event — specifically, from the
`Fail` state that terminates the execution.

For that information to be present, the workflow's `Catch` block must route
the error into a `Fail` state using `ErrorPath` and `CausePath` (not the
static `Error`/`Cause` fields), so the error name and cause are extracted
from the state input at runtime:

```json
"Catch": [
  {
    "ErrorEquals": [
      "States.ALL"
    ],
    "Next": "failure",
    "ResultPath": "$.error"
  }
]
```

```json
"failure": {
    "Type": "Fail",
    "ErrorPath": "$.error.Error",
    "CausePath": "$.error.Cause"
}
```

If a failed execution's `Fail` state does not use `ErrorPath`/`CausePath`,
`update-state` records a placeholder cause noting that the workflow
definition is missing these fields.

See the AWS documentation for the [Fail workflow state](https://docs.aws.amazon.com/step-functions/latest/dg/state-fail.html).

### Workflow best practices

Cirrus imposes few constraints on workflow structure, favoring flexibility
over guardrails. The following guidelines are not enforced, but help keep a
Cirrus deployment easy to manage.

#### AWS Step Functions best practices

Review AWS's own [best practices for Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/sfn-best-practices.html)
for general considerations, including handling Lambda concurrency quotas
with a `Retry` block as shown above.

#### Prefer one input item per workflow

State tracking and execution management are easier to follow when a
workflow processes a single input item. Where multiple inputs are
unavoidable, using a synthetic item (an AOI item, a list item) that resolves
the full set of inputs is one way to keep a single-item workflow interface
while still processing many items. The synthetic item should resolve the
same set of inputs deterministically.

#### Keep workflows short and focused

A workflow should model a single level of processing. If a workflow needs to
persist intermediate outputs partway through, that's a sign it should be
split into multiple workflows chained together, with a final workflow
producing the actual outputs.

#### Workflows should not produce different outputs from the same set of inputs

See the [Cirrus Payload docs](../../cirrus/30_payload.md) for how Cirrus's
idempotency check works: Cirrus uses the set of input items as a proxy for a
workflow's outputs. Don't rely on workflow or task parameters to change the
set of outputs, since those settings are not part of the idempotency check.

#### Make workflows specific, not flexible

Using process-definition parameters to control dynamic behavior within a
workflow is tempting, but generally best avoided:

- Dynamism within a workflow means different executions of the same
  workflow can't be assumed to have done the same thing, raising the
  cognitive load of troubleshooting and pipeline management.
- Dynamic workflows can require running the same workflow multiple times to
  produce different sets of outputs, conflicting with the idempotency
  guideline above.

Restrict dynamic parameters to those that don't affect the type or contents
of the output items.

#### Don't use workflows for side effects

Workflows are functional processing units that transform inputs into a
fixed set of outputs. Using a workflow purely to trigger a side effect for
every payload — already processed, in processing, or new — is a Cirrus
anti-pattern; use an event-based solution outside the workflow instead.
