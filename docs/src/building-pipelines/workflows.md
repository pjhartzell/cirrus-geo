# Defining a workflow

A workflow is an [AWS Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) state machine, written in [Amazon States Language](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-amazon-states-language.html), that runs a payload through a sequence of tasks. Cirrus starts an execution of it per payload and records the outcome. Everything between start and finish is the state machine's own definition.

A workflow deploys as its own CloudFormation stack containing an `AWS::StepFunctions::StateMachine` and the IAM role it assumes to invoke its tasks. The in-repo `minimal` workflow (`cloudformation/workflows/minimal/state_machine.yaml`) is the smallest complete example: one `Choice` state that succeeds or fails on a field in the payload, with no tasks at all.

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

Because `minimal` has no tasks, its `Fail` state can use static `Error` and `Cause` strings. A workflow with tasks should capture the failing task's error instead. See [Capturing errors](#capturing-errors).

## Naming and dispatch

The state machine must be named `${ResourcePrefix}-<workflow>`, where `<workflow>` is the name a payload's process definition uses in its `workflow` field. This convention is the only link between the core stack and a workflow stack:

- The `process` function builds the state machine ARN by appending the workflow name to `CIRRUS_BASE_WORKFLOW_ARN`, which `cloudformation/core/functions.yaml` sets to `arn:aws:states:<region>:<account>:stateMachine:${ResourcePrefix}-`. Its IAM role allows `states:StartExecution` only on ARNs with that prefix.
- The EventBridge rule that invokes `update-state` matches `stateMachineArn` against the same prefix, so a state machine outside the convention finishes without its outcome being recorded.

Workflow names must not contain underscores. The state database joins the collections and workflow name with an underscore and splits on the last one to recover them. See [ID format](../reference/payload-schema.md#id-format).

## State machine structure

Every workflow definition has:

- `StartAt` naming the first state.
- At least one state that ends the execution successfully: `End: true` on a `Task` state, or a `Succeed` state.
- A `Fail` state that each task's `Catch` routes to, so that a task error ends the execution as `FAILED` with the error preserved.

A task that invokes a Lambda function uses the `arn:aws:states:::lambda:invoke` resource with the function ARN in `Parameters.FunctionName`, rather than naming the function ARN as the state's `Resource`. This integration records the Lambda request ID in the execution history, which is what [`get-execution-events --with-log-metadata`](../operating/monitoring.md#isolating-one-lambda-invocation) uses to find the invocation's logs. It also wraps the function's return value in a `Payload` field, so the state needs `"OutputPath": "$.Payload"` to pass the Cirrus Payload itself, and not the invoke response, to the next state or to the execution output.

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
            "OutputPath": "$.Payload",
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

`"Payload.$": "$"` passes the whole state input, the Cirrus Payload, to the function. `update-state` parses the execution's final output as a Cirrus Payload, so the last state's output must be the payload, not a wrapper around it.

A workflow mixes Lambda and Batch tasks freely; Batch is a property of a task, not of the workflow. A Batch task needs `pre-batch` and `post-batch` states around it and a different retry structure. See [Batch tasks in a workflow](batch-workflow-structure.md).

## Retry with backoff and jitter

Some errors occur before a task runs: `Lambda.TooManyRequestsException` when the account's Lambda concurrency is exhausted, or `Batch.AWSBatchException` when the `SubmitJob` rate limit is hit. Retrying immediately tends to fail again for the same reason, so each task's `Retry` should back off:

```json
{
    "ErrorEquals": ["Lambda.TooManyRequestsException", "Lambda.Unknown"],
    "IntervalSeconds": 600,
    "MaxDelaySeconds": 86400,
    "BackoffRate": 2.0,
    "MaxAttempts": 20,
    "JitterStrategy": "FULL"
}
```

`IntervalSeconds` is the first delay. Each later delay is the previous one multiplied by `BackoffRate`, capped at `MaxDelaySeconds`, for up to `MaxAttempts` attempts. `JitterStrategy: FULL` draws each delay at random between zero and the computed value, so many executions that failed together do not retry together. The default, `NONE`, waits the full computed delay every time.

## Capturing errors

`update-state` records a failed execution's error from the `error` and `cause` fields of the EventBridge status-change event. Step Functions fills those from the `Fail` state that ended the execution. For the task's own error to reach the state database, the task's `Catch` must store it in the state and the `Fail` state must read it back with `ErrorPath` and `CausePath`:

```json
"Catch": [
  {
    "ErrorEquals": ["States.ALL"],
    "ResultPath": "$.error",
    "Next": "failure"
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

A `Fail` state with static `Error` and `Cause` strings records those strings instead of the task's error. A `Fail` state with none of these fields leaves `cause` empty, and `update-state` stores a fixed message telling the reader to add `ErrorPath` and `CausePath`. The error name also decides whether the execution is recorded `FAILED` or `INVALID`. See [Lambda functions: Status to state](../reference/lambda-functions.md#status-to-state).

## Triggering workflows off one another

Two ways to model a pipeline as connected workflows:

- **Chaining.** A payload's `process` array lists several process definitions, and the output of each execution becomes the input of the next. See [Chaining workflows](chaining-workflows.md).
- **Publish topic subscriptions.** Any subscriber to the publish SNS topic receives each output item as `update-state` publishes it, and can build and enqueue a new payload from it. This decouples the downstream workflow from the payload that produced the item.

## Design guidance

Cirrus enforces none of the following. They keep a deployment easier to reason about.

**One input item per workflow.** State is tracked per payload ID, and the ID is derived from the input item IDs, so a workflow that takes one item has one record per item and a plain rerun story. Where several inputs are unavoidable, a synthetic item that resolves to the real inputs deterministically keeps the single-item interface.

**Short workflows.** A workflow should model one level of processing. Needing to persist intermediate outputs partway through is a sign it should be two workflows chained together.

**Same inputs, same outputs.** Cirrus decides whether to run a payload from its ID, which encodes only the workflow name, collections, and item IDs. Process definition parameters are not part of that decision, so two submissions that differ only in parameters are the same payload to Cirrus and the second is skipped. Do not rely on parameters to change what a workflow produces.

**Specific over flexible.** Parameters that select between behaviors make executions of the same workflow incomparable and conflict with the rule above. Restrict runtime parameters to values that do not change the type or content of the output items.

**No side-effect workflows.** A workflow transforms an input payload into output items. A workflow whose purpose is a side effect for every payload it sees belongs outside Cirrus, as a subscriber to the publish or workflow event topic.

**Small payloads.** Payloads travel inline through SQS, Step Functions, and EventBridge. Above 120,000 escaped bytes they are swapped for an S3 reference, which adds a round trip to every step, and an output above EventBridge's limit is dropped from the terminal event and never recorded. See [Payload bucket: Oversized payloads](../reference/payload-bucket.md#oversized-payloads).

AWS's [best practices for Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/sfn-best-practices.html) cover the rest.
