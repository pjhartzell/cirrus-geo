# Follow a payload through Cirrus

This page walks one payload through a deployed stack: submit it, watch its state database record change, and fetch its output. It assumes the [Quickstart](quickstart.md) is done, so the main stack and the minimal workflow are deployed and the environment file is sourced. Command options are in the [Command reference](../cli/reference.md); this page is about what happens between the commands.

## Submitting

The quickstart used `run-workflow`, which validates the payload in the shell, submits it, and blocks until the execution finishes. The non-blocking path is `process`, which enqueues the payload and returns. See [Run a workflow and wait for the result](../cli/common-workflows.md#run-a-workflow-and-wait-for-the-result) for how the two differ in where a malformed payload is caught.

Submit the minimal workflow's template payload without waiting, with a unique ID suffix so the run is new:

```bash
<cloudformation/workflows/minimal/payload.json.template cirrus payload template \
    -x id_suffix "-$(uuidgen)" \
    | tee /tmp/payload.json \
    | cirrus manage "$RESOURCE_PREFIX" process
```

The message goes onto `${RESOURCE_PREFIX}-process`. Within a few seconds the `process` function picks it up, validates it, claims it in the state database, uploads the input payload to the payload bucket, and starts the execution.

## Watching state

`get-state` fetches the record. Called right after `process`, the record may not exist yet; the command retries for up to 60 seconds before giving up, so no sleep is needed:

```bash
cirrus manage "$RESOURCE_PREFIX" get-state "$(jq -r .id /tmp/payload.json)"
```

The output is the raw DynamoDB record. The minimal workflow finishes in under a second, so by the time the record is returned it is usually terminal, but a record caught mid-flight looks like this:

```json title="Illustrative record while the execution runs"
{
    "collections_workflow": "collection_minimal",
    "itemids": "item-<uuid>",
    "state_updated": "PROCESSING_2026-08-07T12:00:00+00:00",
    "updated": "2026-08-07T12:00:00+00:00",
    "created": "2026-08-07T11:59:59+00:00",
    "claimed_at": "2026-08-07T11:59:59+00:00",
    "executions": [
        "arn:aws:states:<region>:<account-id>:execution:<prefix>-minimal:<execution-id>"
    ]
}
```

The state is the prefix of `state_updated`. Once `update-state` runs, that prefix becomes `SUCCEEDED`, or `FAILED` with a `last_error` field holding the error name and cause. Every field is described under [State database: Fields](../reference/state-database.md#fields).

Submitting the same payload again with `replace` set appends a second ARN to `executions`. Every command that resolves a payload ID to an execution, including `get-execution` and `get-output-payload`, uses the last one.

The same record is available over HTTP from the [HTTP API](../reference/http-api.md), which returns it in the converted form with `payload_id`, `state`, `input_payload_url`, and `output_payload_url` filled in.

## Fetching the output

Once the record is `SUCCEEDED`:

```bash
cirrus manage "$RESOURCE_PREFIX" get-output-payload "$(jq -r .id /tmp/payload.json)"
```

The command resolves the ID to its most recent execution, builds the output payload's URL from the record, and downloads it. Execution payloads live at `<root>/executions/<payload_id>/<execution_id>/input.json` and `output.json` in the payload bucket, where `<execution_id>` is the Step Functions execution name from the `executions` entry. A failed execution leaves only `input.json`, so `get-output-payload` fails for it while `get-input-payload` still works. See [Payload bucket: Execution payloads](../reference/payload-bucket.md#execution-payloads).

For the execution's own event history and task logs, continue with [Inspect an execution](../cli/common-workflows.md#inspect-an-execution).
