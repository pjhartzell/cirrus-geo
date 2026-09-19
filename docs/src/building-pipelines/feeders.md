# Feeders

A feeder is whatever puts a [Cirrus Payload](../reference/payload-schema.md) on the process queue. Cirrus ships none: `src/` has no feeder base class or CLI subcommand, and `cloudformation/` provisions no feeder resources. Discovering new data, choosing a workflow, and building the payload are the deployment's own code, run on its own compute, whether that is a Lambda function behind an S3 event notification, a scheduled job that polls an external API, or a person running `cirrus manage <deployment> process` from a shell.

## What the queue accepts

The [`process`](../reference/lambda-functions.md#process) function is the queue's only consumer. Its `extract_record` step accepts a message body that is any of:

- a Cirrus Payload, as JSON;
- a reference of the form `{"url": "s3://bucket/key"}` to a payload object, which `process` fetches. Its role can read any bucket, so the object does not have to be in the payload bucket;
- an SNS delivery envelope whose `Message` field holds either of the above, which is what an SNS subscription to the queue produces when raw message delivery is off.

The payload must pass `CirrusPayload.validate`: a `process` array with at least one entry, a `workflow` name in the first entry, and, if present, an `id` in the `<collections>/workflow-<workflow>/<itemids>` form. A missing `id` is generated from the items and workflow name; see [ID format](../reference/payload-schema.md#id-format). A message that cannot be parsed or fails validation is uploaded to the payload bucket's invalid prefix and, after five receives, moved to the dead-letter queue. See [Monitoring: Dead-letter queues](../operating/monitoring.md#dead-letter-queues).

SQS accepts messages up to 256 KB. A larger payload must be stored in S3 and sent as a `{"url": ...}` reference. The Cirrus CLI does this itself, uploading to the payload bucket's oversized prefix, and a Python feeder can do the same with `PayloadBucket.upload_oversize_payload` from `cirrus.lib.payload_bucket`.

## Sending to the queue

The queue is `${ResourcePrefix}-process`. Its URL is the `ProcessQueueUrl` output of the main stack and the `CIRRUS_PROCESS_QUEUE_URL` entry under the deployment's Parameter Store prefix. The feeder's identity needs `sqs:SendMessage` on the queue.

A feeder can also publish to an SNS topic subscribed to the queue, which suits a trigger that already arrives as an SNS notification. No such topic exists in this repository's templates. The two topics the base stack creates, `${ResourcePrefix}-publish` and `${ResourcePrefix}-workflow-event`, are outputs, not inputs. The following is one way to add one, in the style of the templates in `cloudformation/core/`:

```yaml
# Illustrative. Not part of the in-repo templates. ProcessQueueArn and
# ProcessQueueUrl are the base stack outputs of the same names.
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

With `RawMessageDelivery: false`, SNS wraps the published message in its envelope and `process` unwraps it, so the feeder publishes the payload JSON as the message body unchanged.

## A minimal Python feeder

A Lambda handler that takes one STAC item, builds a payload for a workflow named `my-workflow`, and sends it directly to the queue:

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

The `id` is set explicitly because it is one collection and one item. A feeder that submits several items per payload can omit `id` and let `process` derive it, which sorts and joins the collections and item IDs deterministically. A feeder that wants to catch a malformed payload before sending it can call `CirrusPayload(payload).validate()` from `cirrus.lib.cirrus_payload`, which is the same check `process` runs.
