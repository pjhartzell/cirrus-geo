# Feeders

A feeder is any producer that puts a valid [Cirrus Payload](../reference/payload-schema.md)
on the process queue. Cirrus does not ship feeders — there is no feeder
scaffolding, base class, or CloudFormation resource in this repository.
Everything upstream of the process queue (discovering new data, deciding
which workflow to run, building the payload) is left to the deployment.

## What the process Lambda accepts

The process Lambda (`cirrus.lambda_functions.process.lambda_handler`) is the
single consumer of the process queue and the boundary a feeder must satisfy.
For each incoming event it:

1. Normalizes the event into a list of records. An event with a top-level
   `Records` key (SQS or SNS) is iterated record by record; otherwise the
   whole event is treated as one record (`cirrus.lib.utils.normalize_event`).
2. Extracts a payload from each record (`cirrus.lib.utils.extract_record`):
   an SQS record's `body` is JSON-decoded; an SNS record's `Sns.Message` is
   JSON-decoded; a Batch record's `Parameters.url_out` is remapped to
   `{"url": ...}`.
3. If the extracted payload is a `{"url": "s3://..."}` reference rather than
   an inline payload, fetches the full payload from S3
   (`cirrus.lib.utils.payload_from_s3`). This is how oversized payloads are
   handled — see [Oversized Payloads](../reference/payload-bucket.md#oversized-payloads).
4. Constructs a `CirrusPayload` from the result, generating an `id` if one
   is missing, then validates it.
5. Hands valid payloads to `PayloadManagers.process`, which claims each
   payload in the StateDB and starts the workflow's Step Functions
   execution.

A payload that fails extraction or validation is uploaded to the payload
bucket's invalid-payload prefix and does not start a workflow
(`cirrus.lambda_functions.process.lambda_handler`).

### Payload validation

`CirrusPayload.validate` (`cirrus.lib.cirrus_payload.CirrusPayload`) requires:

- A `process` field that is a non-empty array of process definitions.
- A `workflow` field in the first process definition.
- An `id` field matching `<collections>/workflow-<workflow>/<itemids>`.

If `id` is omitted, the process Lambda generates one (`CirrusPayload.set_id`):
`collections` comes from the process definition's `collections` field if
present, otherwise from the sorted, `/`-joined set of `collection` values
across `features`; `itemids` is the sorted, `/`-joined set of item `id`
values from `features`. A feeder that omits `features` entirely cannot rely
on ID generation and must set `id` itself.

## Getting a payload onto the process queue

The process Lambda has an `AWS::Lambda::EventSourceMapping` against the
process queue, batching up to 10 SQS messages per invocation
(`cloudformation/core/functions.yaml`). The queue itself is a plain
`AWS::SQS::Queue` named `${ResourcePrefix}-process`, with a redrive policy to
a dead-letter queue after 5 receive attempts
(`cloudformation/core/base.yaml`).

There is no `AWS::SNS::Subscription` or SNS topic feeding the process queue
anywhere in this repository's CloudFormation. The two SNS topics that do
exist (`PublishTopic`, `WorkflowEventTopic` in `cloudformation/core/base.yaml`)
carry output notifications and workflow state events — they are not inputs
to the process queue. A feeder has two options, given what the process
Lambda actually accepts:

- **Send directly to the process queue** with `sqs:SendMessage`, using the
  message body as the JSON payload. This is the simplest option and matches
  exactly what `extract_record` expects from an SQS record.
- **Subscribe an SNS topic to the process queue**, if a feeder's upstream
  trigger (e.g., an S3 event notification or a separate application) is more
  naturally expressed as an SNS publish. After JSON-decoding an SQS record's
  `body`, `extract_record` also decodes a nested `Message` field — the SNS
  delivery envelope — so this works without changes to the process Lambda.

!!! note
    No SNS topic subscribed to the process queue exists in this repository's
    CloudFormation templates. The snippet below is illustrative, not a
    reference deployment — it shows one way to wire a feeder's own SNS topic
    to the existing process queue, following the style of the templates in
    `cloudformation/core/`.

```yaml
# Illustrative — not part of the in-repo CloudFormation templates.
# ProcessQueueArn and ProcessQueueUrl are the base-stack outputs of the same
# names (cloudformation/core/base.yaml), supplied here as parameters.
Resources:
  NewDataTopic:
    Type: AWS::SNS::Topic
    Properties:
      TopicName: !Sub '${ResourcePrefix}-new-data'

  NewDataToProcessQueue:
    Type: AWS::SNS::Subscription
    Properties:
      TopicArn: !Ref NewDataTopic
      Protocol: sqs
      Endpoint: !Ref ProcessQueueArn
      RawMessageDelivery: false

  ProcessQueuePolicy:
    Type: AWS::SQS::QueuePolicy
    Properties:
      Queues:
        - !Ref ProcessQueueUrl
      PolicyDocument:
        Statement:
          - Effect: Allow
            Principal:
              Service: sns.amazonaws.com
            Action: sqs:SendMessage
            Resource: !Ref ProcessQueueArn
            Condition:
              ArnEquals:
                aws:SourceArn: !Ref NewDataTopic
```

With `RawMessageDelivery: false` (the default), SNS wraps the payload in its
delivery envelope and `extract_record` recovers it from the envelope's
`Message` field — a feeder publishing to `NewDataTopic` publishes the payload
JSON as the SNS message body, unchanged.

## A minimal Python feeder

The following is a plain-boto3 Lambda handler that builds a valid process
payload and sends it directly to the process queue. It takes a single STAC
item and starts a workflow named `my-workflow` for it (substitute a workflow
deployed in your Cirrus instance).

```python
import json
import os

import boto3

sqs = boto3.client("sqs")

QUEUE_URL = os.environ["CIRRUS_PROCESS_QUEUE_URL"]


def build_payload(item: dict) -> dict:
    collection = item["collection"]
    item_id = item["id"]
    workflow = "my-workflow"

    return {
        "type": "FeatureCollection",
        "id": f"{collection}/workflow-{workflow}/{item_id}",
        "features": [item],
        "process": [
            {
                "workflow": workflow,
                "upload_options": {
                    "path_template": "${collection}/${id}",
                },
            },
        ],
    }


def lambda_handler(event, context):
    item = event["item"]
    payload = build_payload(item)

    sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps(payload),
    )

    return payload["id"]
```

`CIRRUS_PROCESS_QUEUE_URL` is the URL of the process queue — the same value
exposed as the `ProcessQueueUrl` stack output in
`cloudformation/core/base.yaml`. The `id` is set explicitly here rather than
left for the process Lambda to generate, since the format
(`<collections>/workflow-<workflow>/<itemids>`) is fixed and simple to
construct from a single item. For a feeder handling multiple items or
collections per payload, omit `id` and provide `features` so the process
Lambda's `CirrusPayload.set_id` generates one, or replicate the same
sorted-join logic if the queue message needs a deterministic ID before
sending.

## Where feeders run

Feeders are not part of the Cirrus deployment. `src/` contains no feeder
package, CLI subcommand, or Lambda template for feeders, and no
CloudFormation template in `cloudformation/` provisions feeder
infrastructure. A feeder is deployed and operated independently of Cirrus,
using its own compute (a separate Lambda function, a container, a scheduled
job) and given permission to call `sqs:SendMessage` on the process queue or
`sns:Publish` on a topic subscribed to it.
