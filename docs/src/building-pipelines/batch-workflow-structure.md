# Wiring a Batch task into a workflow

A Batch task participates in a workflow differently than a Lambda task.
Step Functions invokes Lambda directly and passes the state input as the
Lambda payload; AWS Batch has no equivalent input channel, so a Batch job
submission cannot carry a Cirrus Payload directly. Cirrus works around this
with two built-in Lambda functions, `pre-batch` and `post-batch`, that a
workflow runs immediately before and after each Batch task.

This page covers how a workflow's ASL (Amazon States Language) definition
should be structured around a Batch task. For the CloudFormation resources
behind a Batch task itself — job definitions, compute environments, job
queues, IAM — see [Batch infrastructure](batch-infrastructure.md).

## The `pre-batch`/`post-batch` contract

`pre-batch` uploads the input payload to the payload bucket and returns
`url` and `url_out`; the Batch job reads its input from `url` and must write
its output to `url_out`; `post-batch` reads the output from `url_out` and
returns it to the state machine, or, on job failure, raises the underlying
error from the job's logs. See
[Lambda functions: pre-batch](../reference/lambda-functions.md#pre-batch) and
[post-batch](../reference/lambda-functions.md#post-batch) for the full
contract, including how `post-batch` reconstructs errors from CloudWatch
logs.

A workflow must run `pre-batch` immediately before a Batch task step and
`post-batch` immediately after, passing `url` and `url_out` through the
Batch task's parameters so `post-batch` can find the output.

## Group the three steps in a `Parallel` block

A Batch task in a workflow is really three Step Functions steps:
`pre-batch`, the Batch task, and `post-batch`. Because they only make sense
together, they should share error handling and retries — if any one of the
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
with a fixed string — see [Workflows: Capturing
errors](workflows.md#capturing-errors) for why this matters and how
`update-state` consumes it.

For retry `IntervalSeconds`/`BackoffRate`/`MaxAttempts`/`JitterStrategy`
semantics, see [Workflows: Retry with backoff and
jitter](workflows.md#retry-with-backoff-and-jitter).

### Example

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
                                "JobQueue": "#{ExampleJobQueue}",
                                "JobDefinition": "#{ExampleBatchJob}",
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

## When Batch overhead dominates

Submitting and scheduling a Batch job carries overhead — job placement onto
a compute resource can take minutes — that is fixed regardless of how long
the job itself runs. When a task's actual work is short, that overhead can
dominate the total runtime and cost, which is a signal to use a Lambda task
instead (see [Tasks: Lambda vs Batch](tasks.md#lambda-vs-batch)). Two
examples from Earth Search:

- Ingesting Landsat's `public-c2-notify-v2` SNS topic includes many
  "Real-Time" scenes that are filtered out after a few seconds of work.
  Running that filtering step as a Batch job would spend minutes of job
  placement overhead (and the corresponding EC2 cost) on a few seconds of
  actual use. More generally, Landsat ingest uses Lambda rather than Batch
  throughout, since it performs only a metadata-to-metadata conversion
  taking tens of seconds per scene — well under the Lambda timeout, and
  consistent enough that Batch's overhead is never worth it.
- The Sentinel-2 Collection 1 Level-2A collection only includes items with a
  processing baseline of 05.00 or higher. When back-processing the full
  catalog, roughly half the scenes had an older baseline and were discarded
  immediately, while the other half ran a full 5-10 minute Batch job. The
  discarded half still paid Batch's placement overhead, increasing cost and
  reducing throughput. A Lambda step to check the processing baseline first,
  ahead of the Batch job, would have avoided that cost for the discarded
  half.

## Batch errors and `InvalidInput`

A task that determines its input can never be processed — as opposed to a
transient or code failure — should raise the same `InvalidInput` exception
used by Lambda tasks so the execution is recorded as `INVALID` rather than
`FAILED`; see [Lambda functions: update-state](../reference/lambda-functions.md#update-state)
for the exception classes recognized and how the distinction is used.
