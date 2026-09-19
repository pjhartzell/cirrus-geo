# Batch tasks in a workflow

Step Functions passes a Lambda task its input directly. AWS Batch has no equivalent channel: a `SubmitJob` request carries only small string parameters, not a Cirrus Payload. Cirrus bridges the gap with two core Lambda functions, [`pre-batch`](../reference/lambda-functions.md#pre-batch) and [`post-batch`](../reference/lambda-functions.md#post-batch), that the workflow runs immediately before and after each Batch task.

This page covers the state machine definition around a Batch task. The CloudFormation for the task itself, meaning the job definition, compute environment, job queue, and IAM, is in [Batch infrastructure](batch-infrastructure.md).

## The contract

`pre-batch` uploads the state input to S3 and returns `{"url": ..., "url_out": ...}`. The Batch job reads its input payload from `url` and writes its output payload to `url_out`. `post-batch` reads `url_out` and returns the payload to the state machine, so the next state receives a Cirrus Payload as it would from a Lambda task. The workflow's job is to pass `url` and `url_out` from `pre-batch`'s output into the Batch task's `Parameters`, and to route a failed job's error into `post-batch` so it can surface the job's own exception. See [Lambda functions](../reference/lambda-functions.md#pre-batch) for what each function does with failures.

## Group the three steps in a `Parallel` block

A Batch task in a workflow is really three Step Functions steps:
`pre-batch`, the Batch task, and `post-batch`. Because they only make sense
together, they should share error handling and retries: if any one of the
three fails in a way that isn't retried, the whole group should fail.

Step Functions' `Parallel` state supports `Retry` and `Catch` like a `Task`
state, and accepts one or more branches. Using `Parallel` with a single
branch groups the three steps into one unit from the perspective of retries
and failure, without actually running anything concurrently.

### Error handling

Failures are more varied with Batch than with Lambda. A `SubmitJob` call can
fail with `Batch.AWSBatchException` when too many jobs are submitted too
quickly. A running job can be killed and need to be retried when its
underlying EC2 instance is reclaimed, which happens routinely with Spot
instances at scale. Wrapping the Batch task step in a `Parallel` block with a
`Retry` policy handles both cases without retrying `pre-batch` or
`post-batch` unnecessarily.

The `Parallel` block's own `Catch` must route to a `Fail` state that uses
`ErrorPath`/`CausePath` (not static `Error`/`Cause`) so the error captured
from a failed Batch job or Lambda function is preserved rather than replaced
with a fixed string. See [Workflows: Capturing
errors](workflows.md#capturing-errors) for why this matters and how
`update-state` consumes it.

For retry `IntervalSeconds`/`BackoffRate`/`MaxAttempts`/`JitterStrategy`
semantics, see [Workflows: Retry with backoff and
jitter](workflows.md#retry-with-backoff-and-jitter).

### Example

The definition below is written as the body of a CloudFormation `!Sub`, so `${ExampleJobQueue}` and `${ExampleBatchJob}` resolve to the job queue and job definition resources in the same template.

```json
{
    "Comment": "Example workflow using Parallel to group a Batch task with pre-batch/post-batch",
    "StartAt": "batch-group",
    "States": {
        "batch-group": {
            "Type": "Parallel",
            "Branches": [
                {
                    "StartAt": "pre-batch",
                    "States": {
                        "pre-batch": {
                            "Type": "Task",
                            "Resource": "arn:aws:states:::lambda:invoke",
                            "Parameters": {
                                "FunctionName": "arn:aws:lambda:us-east-1:123456789012:function:my-prefix-pre-batch",
                                "Payload.$": "$"
                            },
                            "OutputPath": "$.Payload",
                            "Next": "batch-task",
                            "Retry": [
                                {
                                    "ErrorEquals": [
                                        "Lambda.TooManyRequestsException",
                                        "Lambda.Unknown"
                                    ],
                                    "IntervalSeconds": 10,
                                    "MaxDelaySeconds": 86400,
                                    "BackoffRate": 2,
                                    "MaxAttempts": 20,
                                    "JitterStrategy": "FULL"
                                }
                            ]
                        },
                        "batch-task": {
                            "Type": "Task",
                            "Resource": "arn:aws:states:::batch:submitJob.sync",
                            "Parameters": {
                                "JobName": "some-batch-job",
                                "JobQueue": "${ExampleJobQueue}",
                                "JobDefinition": "${ExampleBatchJob}",
                                "Parameters": {
                                    "url.$": "$.url",
                                    "url_out.$": "$.url_out"
                                }
                            },
                            "Next": "post-batch",
                            "Retry": [
                                {
                                    "ErrorEquals": [
                                        "Batch.AWSBatchException"
                                    ],
                                    "IntervalSeconds": 600,
                                    "MaxDelaySeconds": 86400,
                                    "BackoffRate": 2,
                                    "MaxAttempts": 20,
                                    "JitterStrategy": "FULL"
                                }
                            ],
                            "Catch": [
                                {
                                    "ErrorEquals": [
                                        "States.ALL"
                                    ],
                                    "ResultPath": "$.error",
                                    "Next": "post-batch"
                                }
                            ]
                        },
                        "post-batch": {
                            "Type": "Task",
                            "Resource": "arn:aws:states:::lambda:invoke",
                            "Parameters": {
                                "FunctionName": "arn:aws:lambda:us-east-1:123456789012:function:my-prefix-post-batch",
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
                                    "IntervalSeconds": 10,
                                    "MaxDelaySeconds": 86400,
                                    "BackoffRate": 2,
                                    "MaxAttempts": 20,
                                    "JitterStrategy": "FULL"
                                }
                            ]
                        }
                    }
                }
            ],
            "Next": "publish",
            "OutputPath": "$[0]",
            "Retry": [
                {
                    "ErrorEquals": [
                        "States.ALL"
                    ],
                    "MaxAttempts": 3,
                    "IntervalSeconds": 1200,
                    "MaxDelaySeconds": 86400,
                    "BackoffRate": 2,
                    "JitterStrategy": "FULL"
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
        "publish": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {
                "FunctionName": "arn:aws:lambda:us-east-1:123456789012:function:my-prefix-publish",
                "Payload.$": "$"
            },
            "End": true,
            "Retry": [
                {
                    "ErrorEquals": [
                        "Lambda.TooManyRequestsException",
                        "Lambda.Unknown"
                    ],
                    "IntervalSeconds": 10,
                    "MaxDelaySeconds": 86400,
                    "BackoffRate": 2,
                    "MaxAttempts": 20,
                    "JitterStrategy": "FULL"
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

The Batch task step catches its own errors (`Catch` routing to `post-batch`
on `States.ALL`) so that `post-batch` always runs, even after a Batch job
failure, and can turn the raw Batch failure into the underlying container
error before it propagates further. The outer `Parallel` block then retries
or fails the whole `pre-batch`/Batch/`post-batch` group as a unit.

## Batch retries vs. Step Functions retries

Prefer Step Functions' `Retry` (as above) over relying on AWS Batch's own
job retry configuration. Batch retries apply uniformly regardless of failure
reason, while Step Functions `Retry` blocks match specific error types,
giving more control over what gets retried versus failed outright.
Step Functions retries also appear as distinct steps in the execution
history, making a retried attempt and its original failure visible to anyone
investigating the run; Batch's own retries are internal to the job and are
not reflected in the state machine execution.

## Batch errors and `InvalidInput`

A Batch task that finds its input unprocessable should raise `stactask.exceptions.InvalidInput` like a Lambda task would. `post-batch` reads the job's last log line, which for an uncaught Python exception is `stactask.exceptions.InvalidInput: <message>`, and re-raises it under that name, so `update-state` records the execution as `INVALID` rather than `FAILED`. See [Raising InvalidInput](tasks.md#raising-invalidinput).
