# Publish topic

The publish topic is where a Cirrus deployment's output leaves it. When an execution succeeds, [`update-state`](lambda-functions.md#on-success) publishes every item in the output payload's `features` to this SNS topic, one message per item. Anything downstream, a STAC API ingest, a feeder for another pipeline, an archive, subscribes here.

The reference templates create the topic as `${ResourcePrefix}-publish` in `cloudformation/core/base.yaml` and pass its ARN to `update-state` as `CIRRUS_PUBLISH_TOPIC_ARN`. When that variable is unset, nothing is published.

## When items are published

Publishing happens after the state database records `SUCCEEDED` and the output payload is uploaded, and only when the execution produced an output payload. A `FAILED`, `INVALID`, or `ABORTED` execution publishes nothing. Items are published as the final task returned them; Cirrus does not validate them as STAC. Messages are sent in batches of up to ten with `PublishBatch`, and a batch publish failure leaves the record `SUCCEEDED`, so a subscriber cannot assume it saw every succeeded execution's items.

## Message body

The message body is the item's JSON, unchanged from the output payload. A subscriber that wants the whole output payload rather than one item at a time reads it from the payload bucket instead; the execution's `output.json` URL is on the state database record and on the `SUCCEEDED` [workflow event](workflow-events.md).

## Message attributes

`cirrus.lib.utils.build_item_sns_attributes` sets these attributes on each message, each only when the item has the field it comes from. They exist so a subscription filter policy can select items without parsing bodies.

| Attribute | Type | Source |
| --- | --- | --- |
| `collection` | String | The item's `collection` |
| `bbox.ll_lon`, `bbox.ll_lat`, `bbox.ur_lon`, `bbox.ur_lat` | Number | The four values of the item's `bbox` |
| `datetime` | String | `properties.datetime` |
| `start_datetime` | String | `properties.start_datetime`, or `properties.datetime` when the former is absent |
| `end_datetime` | String | `properties.end_datetime`, or `properties.datetime` when the former is absent |
| `cloud_cover` | Number | `properties.eo:cloud_cover` |
| `status` | String | `created` when `properties.created` equals `properties.updated`, `updated` when they differ. Absent when either field is missing |

That is ten attributes at most, which is the limit SNS enforces for delivery to an SQS queue with raw message delivery.

## Subscribing

An SQS queue is the usual subscriber, since it buffers items for a consumer that processes them in its own time. A filter policy on the subscription narrows what the queue receives. To receive only items from one collection with cloud cover under 20 percent:

```json
{
  "collection": ["sentinel-2-l2a"],
  "cloud_cover": [{"numeric": ["<", 20]}]
}
```

With raw message delivery enabled on the subscription, the queue receives the item JSON as the message body and the attributes as SQS message attributes. Without it, SNS wraps the item in its delivery envelope, with the item under `Message` and the attributes under `MessageAttributes`.

A [feeder](../building-pipelines/feeders.md) that builds a new payload from each published item is how one pipeline triggers another without [chaining](../building-pipelines/chaining-workflows.md), and the publish topic is where a workflow event subscriber should not look for output: workflow events carry state changes and payload URLs, not items.
