# Follow a payload through Cirrus

This walks a single payload through a deployed Cirrus stack: submit it,
watch it move through the state database, and retrieve its output. It
assumes you've already completed the [Quickstart](quickstart.md) — the main
stack and the minimal workflow stack are deployed, `.env.aws` (or
`.env.localstack`) is sourced, and you've submitted at least one payload with
`run-workflow`.

For command syntax and flags, see the [CLI cookbook](../cli/common-workflows.md)
and the [CLI reference](../cli/reference.md). This page is about what happens
between those commands.

## Submission: two paths, two validation points

The quickstart's [submit a test payload](quickstart.md#6-submit-a-test-payload)
step uses `run-workflow`, which blocks until the execution reaches a terminal
state. There's also a non-blocking path, `process`, which enqueues a payload
and returns immediately — see
[Run a workflow and wait for the result](../cli/common-workflows.md#run-a-workflow-and-wait-for-the-result)
in the cookbook for both.

The two commands validate differently:

!!! note
    `run-workflow` validates the payload client-side (`CirrusPayload.validate`)
    before submitting it — a payload missing `process` or a `workflow` name,
    or with an `id` that doesn't match `<collections>/workflow-<workflow>/<itemids>`,
    is rejected before it ever reaches AWS. `process` performs no client-side
    validation: it enqueues the payload as-is, and validation happens in the
    process Lambda, which routes an invalid payload to the payload bucket's
    invalid-payload prefix without starting a workflow.

That difference matters for how you find out something is wrong: a bad
payload piped into `run-workflow` fails immediately, in your shell, with the
validation error. The same payload piped into `process` is accepted, enqueued,
and only rejected once the process Lambda picks it up — you won't see that
rejection unless you go looking (`get-state` will never show a record for it,
since it never reached the state database; check the invalid-payload prefix
in the payload bucket instead).

## Watching state

`get-state` fetches a payload's state database record. If you call it
immediately after a non-blocking `process` submission, the record may not
exist yet — the process Lambda hasn't claimed it. `get-state` handles this by
retrying with backoff for up to 60 seconds before giving up, so in practice
you can call it right away rather than adding your own sleep-and-retry loop:

```bash
cirrus manage "$RESOURCE_PREFIX" get-state "collection/workflow-minimal/item-<uuid>"
```

This returns the raw DynamoDB item — see [State Database fields](../reference/state-database.md#fields)
for the full reference. A record mid-processing looks like this (illustrative
values):

```json title="Illustrative — after claim_processing"
{
    "collections_workflow": "collection_minimal",
    "itemids": "item-<uuid>",
    "state_updated": "PROCESSING_2026-08-07T12:00:00+00:00",
    "updated": "2026-08-07T12:00:00+00:00",
    "created": "2026-08-07T11:59:59+00:00",
    "executions": [
        "arn:aws:states:<region>:<account-id>:execution:<prefix>-minimal:<execution-id>"
    ],
    "claimed_at": "2026-08-07T11:59:59+00:00"
}
```

The current state is the prefix of `state_updated` (`PROCESSING` above, split
on `_`). On success, `outputs` (a list of output STAC item URLs) is added; on
failure or invalid input, `last_error` is added instead. `executions`
accumulates one ARN per claim, so a payload rerun with `replace=true` shows
multiple entries — the most recent one is what `get-execution` and the
output-fetching commands resolve against.

The same state is queryable over HTTP, unauthenticated, via API Gateway — see
[API Endpoints](../reference/http-api.md) for the route list. The API's item
responses go through `dbitem_to_item`, which adds `payload_id`, `state`,
`input_payload_url`, and `output_payload_url` fields not present on the raw
`get-state` output above.

For inspecting the Step Functions execution itself (event history, task
logs) and querying many records at once, see
[Inspect an execution](../cli/common-workflows.md#inspect-an-execution) and
[Query the state database in bulk](../cli/common-workflows.md#query-the-state-database-in-bulk)
in the cookbook.

## Fetching the output

Once a record's state is `SUCCEEDED`, `get-output-payload` resolves the
payload ID's most recent execution, looks up its `output_payload_url` in the
state database, and downloads that object from the payload bucket — see
[Check state and stored payloads](../cli/common-workflows.md#check-state-and-stored-payloads)
in the cookbook for the command.

Per the [payload bucket key layout](../reference/payload-bucket.md#execution-payloads),
execution payloads are stored under
`<root_prefix>/executions/<payload_id>/<execution_id>/input.json` and
`.../output.json`, where `<execution_id>` is the Step Functions execution
name. `output.json` is written only on successful completion — a `FAILED`,
`INVALID`, or `ABORTED` execution leaves only `input.json` under that
execution's prefix. Read `<execution_id>` off the record's `executions` entry
rather than constructing it by hand.
