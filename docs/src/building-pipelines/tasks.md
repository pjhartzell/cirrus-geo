# Tasks

Tasks implement a unit of processing, composed together into a
[Workflow](workflows.md). A task takes a [Cirrus Payload](../reference/payload-schema.md)
as input, does its work, and returns a Cirrus Payload as output — making any
required modifications to the payload's items and/or deriving new assets,
which it pushes to their canonical storage location in S3.

To implement custom processing for a pipeline, write a task. The best tasks
are modular, focused, and composable. Most projects end up with more custom
tasks than any other component type.

Tasks run on AWS Lambda and/or AWS Batch. Lambda tasks are simpler to manage
and quicker to start, but Lambda's runtime constraints (timeout, memory,
package size) can rule it out for some workloads. Batch allows longer
runtimes, larger resource limits, and specialized instance types.

## Anatomy of a task

Generally speaking, every task should do a few key things:

- Take an input Cirrus Payload.
  - For Batch tasks and/or large payloads, a task should support receiving
    a `url` input parameter pointing to a payload object in S3.
- Download any required assets from the items in the input payload.
- Perform any asset metadata manipulation and/or derived product processing.
- Update or replace payload items based on the task's outputs.
- Upload any output assets/items to S3 for persistence.
- Return the output Cirrus Payload.
  - For Batch tasks and/or large payloads, a task should support uploading
    the output payload to S3 and returning an output `url` parameter
    pointing to that object.

Certain tasks may deviate from this pattern, but most tasks follow this flow,
in part or in full. The Python [`stac-task`](https://github.com/stac-utils/stac-task)
library (the `stactask` package, a dependency of Cirrus) provides a base
`Task` class with convenience methods for these common actions.

### Lambda tasks

Lambda tasks use the [AWS Lambda](https://docs.aws.amazon.com/lambda/latest/dg/welcome.html)
runtime. Lambda has the advantage of quick startup and easy management, but
carries restrictions like short timeouts and fixed resource limits.

<a id="lambda-logs"></a>

**Logs**

Lambda functions running in AWS write logs to CloudWatch Logs, with all
invocations of a given Lambda function writing to the same log group. When
Lambda reuses execution environments, multiple invocations write to the same
log stream, potentially interleaving their logs and making it difficult to
isolate logs for a specific invocation.

Each Lambda invocation has a unique request ID (provided in the Lambda
context parameter as `context.aws_request_id`) that can be injected into log
messages to enable filtering. For example, you can use the AWS CLI to filter
logs by request ID:

``` bash
aws logs filter-log-events \
    --log-group-name '/aws/lambda/cirrus-pre-batch' \
    --filter-pattern '5ebd5f70-6dbe-4ea5-bd81-e5b69a4d0824'
```

where the `--filter-pattern` value is the Lambda request ID.

When Lambda tasks are invoked in Step Functions using the
`arn:aws:states:::lambda:invoke` resource pattern (as shown in the
[workflow definitions](workflows.md) documentation), the request ID is
exposed in the Step Functions execution history metadata. The
`get-execution-events` management command with the `--with-log-metadata`
flag retrieves this metadata, and the `get-lambda-logs` command uses the
request ID to filter CloudWatch logs for a specific Lambda invocation. See
the [CLI commands](../cli/common-workflows.md) documentation for usage
examples.

### Batch tasks

Batch tasks use [AWS Batch](https://docs.aws.amazon.com/batch/latest/userguide/what-is-batch.html)
semantics to define [jobs](https://docs.aws.amazon.com/batch/latest/userguide/jobs.html)
that execute within a [compute environment](https://docs.aws.amazon.com/batch/latest/userguide/compute_environments.html)
as determined by the [job queue](https://docs.aws.amazon.com/batch/latest/userguide/job_queues.html)
to which the job is submitted. Batch compute environments can use
[Fargate](https://docs.aws.amazon.com/eks/latest/userguide/fargate.html) or
[EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/concepts.html) to
run jobs, allowing significantly more control over the execution environment
than Lambda, as well as much greater resource limits.

A Batch task is not a single CloudFormation resource: at minimum it needs a
Batch [job definition](https://docs.aws.amazon.com/batch/latest/userguide/job_definitions.html),
but commonly also a job queue, compute environment, and supporting IAM roles.
A workflow's Batch step also relies on the `pre-batch` and `post-batch`
Lambda functions to move the payload into and out of the job, since a Batch
job submission cannot carry a large JSON payload directly — see
[Lambda functions: pre-batch](../reference/lambda-functions.md#pre-batch) and
[post-batch](../reference/lambda-functions.md#post-batch).

For declaring the CloudFormation resources behind a Batch task, see
[Batch infrastructure](batch-infrastructure.md).

A task running in Batch that determines its input can never be processed
should raise the same `InvalidInput` exception a Lambda task would (see
[Logging and error contract](#logging-and-error-contract) below) so the
execution is recorded as `INVALID` rather than `FAILED` — see
[Batch workflow structure: Batch errors and `InvalidInput`](batch-workflow-structure.md#batch-errors-and-invalidinput).

## Lambda vs Batch

Either can be run from the same underlying Docker image build (see
[Docker image](#docker-image) below), so the choice comes down to runtime
constraints.

Choose Lambda when the task:

- has a short runtime, no more than 15 minutes
- runs fine on a single vCPU
- fits under 10 GB of memory
- has a small code size and few dependencies
- needs its code to live in the Cirrus project repository

Choose Batch when the task:

- always runs longer than 5 minutes
- has a larger package size or many dependencies
- needs multiple vCPUs, more than 10 GB memory, or a specific vCPU-to-memory
  ratio
- is easier to manage as a separate container image
- needs more than 10 GB of storage
- needs special hardware (for example, a GPU)

## Docker image

Using a Docker image for a task is recommended unless the task is intended
to run only in Lambda and has few dependencies — rarely the case with
geospatial processing.

The easiest way to do this is to create a Python class that extends
`stactask.task.Task` and implements the abstract method
`def process(self, **kwargs: Any) -> List[Dict[str, Any]]`. Put this class in
`src/task/task.py`, and invoke it from Docker with:

```
FROM public.ecr.aws/lambda/python:3.11

# ENTRYPOINT ["/lambda-entrypoint.sh"] # set by base lambda image
COPY src/task/task.py ${LAMBDA_TASK_ROOT}/task.py
CMD [ "task.handler" ]
```

If you use a container that is not based on a standard Lambda image, you
must add the `lambda-entrypoint.sh` file to your image and set `ENTRYPOINT`
explicitly.

The same Docker image cannot be used by both Batch and Lambda, since they
require different `CMD`/`ENTRYPOINT` settings. The solution is a base image
with every directive except `CMD` and `ENTRYPOINT`, and two derived images
that set those directives for each target. For a base image built on a
standard AWS Lambda image (`public.ecr.aws/lambda/python:3.11`):

Batch:

```
COPY src/task/task.py ${LAMBDA_TASK_ROOT}/task.py
ENTRYPOINT []
```

(any prior `CMD` is reset by the `ENTRYPOINT` change; the command to run is
set by the Batch job definition instead)

Lambda:

```
COPY src/task/task.py ${LAMBDA_TASK_ROOT}/task.py
CMD [ "task.handler" ]
```

(the base image sets `ENTRYPOINT ["/lambda-entrypoint.sh"]`)

An example base image that needs geospatial tools could look like this:

```
FROM ghcr.io/lambgeo/lambda-gdal:3.8-python3.11 as gdal

FROM public.ecr.aws/lambda/python:3.11

# Bring C libs from lambgeo/lambda-gdal image
COPY --from=gdal /opt/lib/ ${LAMBDA_TASK_ROOT}/lib/
COPY --from=gdal /opt/include/ ${LAMBDA_TASK_ROOT}/include/
COPY --from=gdal /opt/share/ ${LAMBDA_TASK_ROOT}/share/
COPY --from=gdal /opt/bin/ ${LAMBDA_TASK_ROOT}/bin/

ENV \
  GDAL_DATA=${LAMBDA_TASK_ROOT}/share/gdal \
  PROJ_LIB=${LAMBDA_TASK_ROOT}/share/proj \
  GDAL_CONFIG=${LAMBDA_TASK_ROOT}/bin/gdal-config \
  GEOS_CONFIG=${LAMBDA_TASK_ROOT}/bin/geos-config \
  PATH=${LAMBDA_TASK_ROOT}/bin:$PATH

RUN yum update -y && \
    yum install -y libxml2-devel libxslt-devel python-devel gcc && \
    yum clean all && \
    rm -rf /var/cache/yum /var/lib/yum/history

COPY requirements.txt ${LAMBDA_TASK_ROOT}

RUN pip3 install --no-cache-dir -r requirements.txt

COPY src/task/task.py ${LAMBDA_TASK_ROOT}/task.py
```

Build and tag that as the base image, then build the Lambda and/or Batch
images from it:

Batch:

```
FROM my_base_task

ENTRYPOINT []
```

Lambda:

```
FROM my_base_task

CMD [ "task.handler" ]
```

If only one of Batch or Lambda is needed, these directives can be folded
into a single image definition.

## Task parameters

Tasks can take arguments at runtime via process definition parameters. See
the [Cirrus Payload](../reference/payload-schema.md) docs for more
information.

## Logging and error contract

### Structured logging

Cirrus configures Python's `logging` module so that any logger named under
one of these parent names gets structured JSON output (via `pythonjsonlogger`)
sent to a stream handler, at a level controlled by the `CIRRUS_LOG_LEVEL`
environment variable (default `DEBUG`):

- `task`
- `feeder`
- `function`
- `lambda_function`
- `cirrus.lib`

This configuration lives in `cirrus.lib.logging` and is applied at import
time. To get structured logging in a task, name the logger (or a child
logger, e.g. `task.my-task`) under one of these prefixes.

`cirrus.lib.logging.CirrusLoggerAdapter` wraps a logger and adds Cirrus
context to every message: when constructed with a `payload` dict, it attaches
the payload's `id` and `stac_version` as extra log fields, and an
`aws_request_id` if one is passed in. It also disables propagation from the
logger's parent when that parent is one of the configured names above, which
prevents duplicate log lines in CloudWatch:

```python
from cirrus.lib.logging import CirrusLoggerAdapter

logger = CirrusLoggerAdapter("task.my-task", payload=payload)

logger.info("processing %d items", len(payload["features"]))
```

Every log record from this adapter carries the payload `id` as structured
context, which makes it possible to filter logs for a specific execution
alongside the Lambda request ID (see [Logs](#lambda-logs) above).

### Raising `InvalidInput`

If a task determines its input can never be processed — as opposed to a
transient failure — it should raise `stactask.exceptions.InvalidInput`. The
`update-state` Lambda function recognizes this exception type and records
the execution as `INVALID` instead of `FAILED`. See
[Lambda functions: update-state](../reference/lambda-functions.md#update-state)
for the full FAILED/INVALID mechanism and the state database's use of the
distinction.
