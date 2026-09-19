# Writing a task

A task is one processing step in a workflow. It takes a [Cirrus Payload](../reference/payload-schema.md) in and returns one, modifying the items and writing any assets it produces to S3 on the way. Tasks are the code a pipeline is mostly made of. Cirrus does not define a task interface beyond the payload contract, so a task is any Lambda function or Batch job the workflow's state machine can invoke.

## What a task does

1. Receive a Cirrus Payload. For a Lambda task this is the state input. For a Batch task it is the S3 URL in the `url` job parameter.
2. Read the parameters meant for it from the process definition.
3. Download whatever assets it needs from the items in `features`.
4. Do the processing: derive new assets, compute new metadata, or transform metadata into STAC.
5. Upload output assets to S3 and update the items' asset `href`s to point at them.
6. Return the payload with `features` replaced by the output items. A Lambda task returns it as its response. A Batch task writes it to the URL in the `url_out` job parameter.

[stac-task](https://github.com/stac-utils/stac-task), a dependency of Cirrus, provides a `Task` base class that handles everything but step 4. Subclass it, set a `name` class attribute, and implement `process`, which receives the task's parameters as keyword arguments and returns the output items as dicts:

```python
from typing import Any

from stactask import Task


class MyTask(Task):
    name = "my-task"
    description = "One sentence for --help"

    def process(self, **kwargs: Any) -> list[dict[str, Any]]:
        items = self.items_as_dicts
        ...
        return items


handler = MyTask.handler
```

`Task.handler` is the Lambda entry point. It reads a `{"url": ...}` input by fetching that object, which is how an [oversized payload](../reference/payload-bucket.md#oversized-payloads) arrives, and after `process` returns it applies the process definition's `collection_matchers` to the output items and returns the payload. `Task.cli` is the Batch entry point: `python task.py run <input-url> --output <output-url>` reads the input from the first URL and writes the output payload to the second. The handler does not write an oversized output back to S3; a Lambda task whose output could exceed the size limit should be a Batch task instead.

## Task parameters

A task reads its parameters from `Task.parameters`, which merges the process definition's `workflow_options` with the task's own entry under `tasks`, keyed by the task's `name`, with the task's entry winning on conflicts. Both are described under [Process definition](../reference/payload-schema.md#process-definition).

## Lambda or Batch

A task runs as a Lambda function or an AWS Batch job. Both can be built from one container image; the choice is about runtime limits.

Lambda suits a task that finishes within the 15-minute maximum timeout and fits in 10 GB of memory and 10 GB of ephemeral storage. Lambda sets CPU in proportion to memory, so a task cannot choose its core count. Batch suits a task that runs longer, needs more memory or storage, a specific vCPU-to-memory ratio, or a GPU. A Batch task also needs [its own CloudFormation resources](batch-infrastructure.md) and the [`pre-batch` and `post-batch` states](batch-workflow-structure.md) around it in the workflow, so Lambda is the lower-overhead default.

### When Batch overhead dominates

Submitting a Batch job carries a fixed cost, since placing the job on an instance can take minutes, regardless of how long the job itself runs. When a task's real work is short, that overhead dominates its runtime and cost, and it should be a Lambda task. Two cases from Earth Search:

- Landsat ingest reads the `public-c2-notify-v2` SNS topic, which includes many Real-Time scenes that are filtered out after seconds of work. Running that filter as a Batch job would spend minutes of placement, and the corresponding EC2 cost, on each. Landsat ingest as a whole is a metadata-to-metadata conversion taking tens of seconds per scene, so it runs entirely on Lambda.
- The Sentinel-2 Collection 1 Level-2A collection includes only items with processing baseline 05.00 or higher. During a full back-processing run, roughly half the scenes had an older baseline and were discarded immediately, while the rest ran a five-to-ten-minute Batch job. The discarded half still paid the placement overhead. A Lambda step checking the baseline ahead of the Batch job would have avoided it.

## Container image

Package a task as a container image unless it will only ever run on Lambda and has few dependencies, which is rare for geospatial processing. Lambda and Batch need different `ENTRYPOINT` and `CMD` settings, so build one base image with everything else and derive two thin images from it.

A base image built on the AWS Lambda Python image already has `ENTRYPOINT ["/lambda-entrypoint.sh"]`, the runtime interface client that Lambda requires. The example below adds GDAL from a prebuilt layer image and the task's dependencies:

```dockerfile
FROM ghcr.io/lambgeo/lambda-gdal:3.8-python3.11 AS gdal

FROM public.ecr.aws/lambda/python:3.11

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

COPY requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip3 install --no-cache-dir -r requirements.txt

COPY src/task/task.py ${LAMBDA_TASK_ROOT}/task.py
```

The Lambda image keeps the inherited entrypoint and names the handler:

```dockerfile
FROM my-base-task

CMD [ "task.handler" ]
```

The Batch image clears the entrypoint so the job definition's `Command` runs directly:

```dockerfile
FROM my-base-task

ENTRYPOINT []
```

Clearing `ENTRYPOINT` also resets any inherited `CMD`. The job definition supplies the command, for example `python task.py run Ref::url --output Ref::url_out`; see [Batch infrastructure: Job definition](batch-infrastructure.md#job-definition). A base image that is not derived from an AWS Lambda image must add the Lambda runtime interface client itself for the Lambda variant to work.

## Structured logging

`cirrus.lib.logging` configures Python's `logging` module at import time. Loggers named `task`, `feeder`, `function`, `lambda_function`, `cirrus.lib`, and their children, get JSON output through `pythonjsonlogger` at the level in `CIRRUS_LOG_LEVEL`, default `DEBUG`. A task gets structured logging by naming its logger under one of those prefixes.

`CirrusLoggerAdapter` wraps such a logger and attaches the payload's `id` and `stac_version` to every record when constructed with the payload, plus `aws_request_id` when given one:

```python
from cirrus.lib.logging import CirrusLoggerAdapter

logger = CirrusLoggerAdapter("task.my-task", payload=payload)

logger.info("processing %d items", len(payload["features"]))
```

The adapter also stops the parent logger from propagating to the root logger, which prevents each line appearing twice in CloudWatch under Lambda's own root handler. Filtering a log group by payload ID is then a search for that ID string; see [Isolating one Lambda invocation](../operating/monitoring.md#isolating-one-lambda-invocation).

A task built on stac-task gets a logger named after its `name` attribute through the base class. That logger is not under a Cirrus prefix, so to get Cirrus's JSON format a stac-task task should name itself `task.<something>` or wrap `logging.getLogger("task." + self.name)` itself.

## Raising `InvalidInput`

When a task determines that its input can never be processed, as opposed to failing for a transient reason, it should raise `stactask.exceptions.InvalidInput`. `update-state` recognizes that error name and records the execution as `INVALID` instead of `FAILED`, and `process` will not rerun an `INVALID` payload unless the process definition sets `replace`. Any other exception records `FAILED`, which reruns on resubmission. See [Lambda functions: Status to state](../reference/lambda-functions.md#status-to-state).

For a Batch task the same rule holds. `post-batch` reads the job's last log line and re-raises the exception under the name it finds there, so an uncaught `InvalidInput` in the container still reaches `update-state` by name.
