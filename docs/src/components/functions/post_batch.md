# post-batch

The `post-batch` Lambda function runs immediately after a Batch task in a
workflow, performing the inverse of [`pre-batch`](pre_batch.md): it reads the
task's output payload from S3 (at the `url_out` location established by
`pre-batch`) and returns it to the Step Functions state machine, so the next
task receives it the same way it would from a Lambda task.

## Error handling

When the Batch job fails, `post-batch` reconstructs the underlying error so
it surfaces in the Step Functions execution rather than a generic Batch
failure:

1. It reads the last log event from the job's final attempt in the
   `/aws/batch/job` CloudWatch log group.
2. It parses the error type and message from that log line and re-raises the
   error under the original type name (falling back to `UnknownError`).
3. If the log stream cannot be read — typically because the container never
   started — it raises an error carrying the Batch container reason and
   attempt status reason instead (e.g. `DockerTimeoutError`, "Task failed to
   start").
