# Tasks

Tasks in Cirrus implement a unit of processing, to be composed together into a
[Workflow](../workflows/index.md). Tasks are expected to support both input
and output formatted as a [Cirrus Payload](../../30_payload.md). As
part of it's processing, a task can make any requisite modifications to its
input payload and/or derive any output assets, pushing them to the canonical
storage location in S3.

In other other words, to implement custom processing routines for a pipeline,
use a task. The best tasks are modular, simple, focused, and composable. Most
projects end up with more custom tasks than other component types, so it pays
to be familiar with the tasks ins and outs.

Tasks can make use of AWS Lambda and/or AWS Batch for execution. Lambda tasks
are simpler to manage and quicker to start up, but the Lambda runtime
constraints can be prohibitive or untenable for some task workloads. In those
cases, Batch allows for extended runtimes, greater resource limits, and
specialized instance types.

## Anatomy of a task

Generally speaking, every task should do a few key things:

- Take an input Cirrus Payload
  - In the case of Batch tasks and/or large payloads, tasks should support
    receiving a `url` input parameter pointing to a payload object in S3
- Download any/all required assets from the items in the input payload
- Perform any asset metadata manipulation and/or derived product processing
- Update/replace payload items based on task outputs
- Upload any output assets/items to S3 for persistence
- Return the output Cirrus Payload
  - In the case of Batch tasks and/or large payloads, tasks should support
    uploading the output payload to S3 and returning an output `url` parameter
    pointing to that payload object in S3

Certain tasks may deviate from this pattern, but the vast majority of tasks will
follow this flow, either in part or in full. The python `stac-task` library
provides convenience classes/methods to help build tasks and easily facilitate
these common actions.

### Lambda tasks

Lambda tasks use the [AWS Lambda](https://docs.aws.amazon.com/lambda/latest/dg/welcome.html) runtime to power executions. Lambda has the
advantage of quick startup and easy management, but has many restrictions like
short timeouts and significant resource limits.

<a id="lambda-logs"></a>

**Logs**

Lambda functions running in AWS write logs to CloudWatch Logs, with all invocations
of a given Lambda function writing to the same log group. When Lambda reuses execution
environments, multiple invocations write to the same log stream, potentially
interleaving their logs and making it difficult to isolate logs for a specific
invocation.

Each Lambda invocation has a unique request ID (provided in the Lambda context
parameter as `context.aws_request_id`) that can be injected into log messages
to enable filtering. For example, you can use the AWS CLI to filter logs by
request ID:

``` bash
aws logs filter-log-events \
    --log-group-name '/aws/lambda/cirrus-pre-batch' \
    --filter-pattern '5ebd5f70-6dbe-4ea5-bd81-e5b69a4d0824'
```

where the `--filter-pattern` value is the Lambda request ID.

When Lambda tasks are invoked in Step Functions using the
`arn:aws:states:::lambda:invoke` resource pattern (as shown in the
[workflow definitions](../workflows/definitions.md) documentation), the request
ID is exposed in the Step Function execution history metadata. The
`get-execution-events` management command with the `--with-log-metadata` flag
retrieves this metadata, and the `get-lambda-logs` command uses the request ID to
filter CloudWatch logs for a specific Lambda invocation. See the
[CLI commands](../../../cli/04_commands.md) documentation for usage examples.

### Batch tasks

Batch tasks use [AWS Batch](https://docs.aws.amazon.com/batch/latest/userguide/what-is-batch.html) semantics to define [jobs](https://docs.aws.amazon.com/batch/latest/userguide/jobs.html) that execute within a
[compute environment](https://docs.aws.amazon.com/batch/latest/userguide/compute_environments.html) as determined by the [job queue](https://docs.aws.amazon.com/batch/latest/userguide/job_queues.html) to which the job is
submitted. Batch compute environments can make use of [Fargate](https://docs.aws.amazon.com/eks/latest/userguide/fargate.html) or [EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/concepts.html) to
run jobs, allowing significantly more control over the execution environment
than Lambda allows, as well as much greater limits on resources.

Batch tasks are inherently just an abstraction around a set of CloudFormation
resources, minimally just a Batch [job definition](https://docs.aws.amazon.com/batch/latest/userguide/job_definitions.html), but commonly also the job
queue, compute environment, and any other required resources.

For more information see the [Batch tasks](batch.md) documentation.

## Lambda vs Batch

### When to chose either

- can be run as a Docker image

### When to choose Lambda

- short runtime, with a maximum of 15 minutes
- single vCPU is acceptable
- under 10GB of memory
- small code size / few dependencies
- need code to live in the cirrus project repository

### When to chose Batch

- runtime always longer than 5 minutes
- larger package size / many dependencies
- need multiple vCPUs, more than 10GB memory, or the ability to more precisely specify a vCPU-to-memory ratio
- easier to manage code as separate container images
- need more than 10GB storage
- need special hardware resources (e.g., GPU)

## Docker Image

It is generally recommended to use a Docker image for tasks unless the task is only
intended to run in Lambda and has few dependencies, which is rarely the case with
geospatial processing.

The easiest way to do this is to create a Python class that extends stactask.task.Task
and implements the abstract method `def process(self, **kwargs: Any) -> List[Dict[str, Any]]`.
This class should be put in the file `src/task/task.py`, and can then be invoked by
Docker with directives:

```
FROM public.ecr.aws/lambda/python:3.11

# ENTRYPOINT ["/lambda-entrypoint.sh"] # set by base lambda image
COPY src/task/task.py ${LAMBDA_TASK_ROOT}/task.py
CMD [ "task.handler" ]
```

If you choose to use your own container that is not based on a standard Lambda image,
you must add the `lambda-entrypoint.sh` file to your image and set `ENTRYPOINT` explicitly.

Unfortunately, the same Docker image cannot be used by both Batch and Lambda, as they
have slightly different requirements for the `CMD` and `ENTRYPOINT` parameters. The
solution to this is to have one base image definition that has all directives exception
`CMD` and `ENTRYPOINT`, and then create two image definitions that use the base image
but set `CMD` and `ENTRYPOINT`. For example, if we had a image that used a standard
AWS lambda image (public.ecr.aws/lambda/python:3.11), we would use these directives for
Batch and Lambda.

Batch:

```
COPY src/task/task.py ${LAMBDA_TASK_ROOT}/task.py
ENTRYPOINT []
```

(any prior `CMD` will be reset by the ENTRYPOINT change, and the command is set by the Batch Job Definition)

Lambda:

```
COPY src/task/task.py ${LAMBDA_TASK_ROOT}/task.py
CMD [ "task.handler" ]
```

(base image sets `ENTRYPOINT ["/lambda-entrypoint.sh"]`)

Thereby, an example base image that needed geospatial tools could look like this:

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

That could be built and tagged as the base image, and then the Lambda and/or Batch images
based on it.

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

Of course, if only one of the Batch or Lambda is needed, these commands can be
into a single definition.

## Task parameters

Tasks can take arguments at runtime via process definition parameters. See the
[Cirrus Payload](../../30_payload.md) docs for more information.
