# pre-batch

The `pre-batch` Lambda function runs immediately before a Batch task in a
workflow, working around an AWS Batch limitation: a Batch job submission
cannot carry a large JSON payload directly, and Cirrus Payloads can be large.

`pre-batch` uploads the input payload to the payload bucket and returns:

- `url`: the S3 URL of the uploaded input payload, passed to the Batch job
  as its input parameter
- `url_out`: the S3 URL (the input URL with an `_out.json` suffix) where the
  Batch task must write its output payload, picked up afterwards by
  [`post-batch`](post_batch.md)
