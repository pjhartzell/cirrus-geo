# End-to-End Walkthrough

This walks a single payload through a deployed Cirrus stack: submit it,
watch it move through the state database, and retrieve its output. It
assumes you've already completed the [Quickstart](quickstart.md) — the
main stack and the minimal workflow stack are deployed, and `.env.aws` (or
`.env.localstack`) is sourced, so `$RESOURCE_PREFIX` and friends are set in
your shell.

All commands below use the Cirrus CLI (`cirrus`). See the
[CLI reference](../cli/using-the-cli.md) for the full command tree.

## 1. Submit a payload

The minimal workflow's payload template
(`cloudformation/workflows/minimal/payload.json.template`) has three
template variables:

```json
{
    "type": "FeatureCollection",
    "features": [],
    "process": [
        {
            "workflow": "minimal",
            "succeed": ${succeed?true},
            "replace": ${replace?false}
        }
    ],
    "id": "collection/workflow-minimal/item${id_suffix?}"
}
```

| Variable | Default | Effect |
| --- | --- | --- |
| `succeed` | `true` | Value the minimal workflow's `Choice` state branches on. |
| `replace` | `false` | Allows resubmitting the same payload ID if set `true`. |
| `id_suffix` | unset | Appended to the payload `id`, letting you mint a distinct payload per submission. |

The `id` is fixed by the template as `collection/workflow-minimal/item<id_suffix>`
— it isn't generated from `features`, since the minimal payload has none.
`cirrus payload get-id` (which derives an ID from `features` and the
`workflow` field when a payload has no `id` yet) isn't needed here, but you
can still run the rendered payload through it to print the ID that's already
present:

```bash
<cloudformation/workflows/minimal/payload.json.template cirrus payload template \
    -x id_suffix "-$(uuidgen)" \
    | cirrus payload get-id
```

This prints the payload ID, e.g. `collection/workflow-minimal/item-<uuid>`
(illustrative — the actual value depends on the `uuidgen` output). Keep it;
you'll use it below to query state and fetch output.

### Blocking submission

`cirrus manage "$RESOURCE_PREFIX" run-workflow` reads a payload from stdin,
submits it, polls the state database until the execution reaches a
terminal state, and prints the output payload:

```bash
<cloudformation/workflows/minimal/payload.json.template cirrus payload template \
    -x id_suffix "-$(uuidgen)" \
    | cirrus manage "$RESOURCE_PREFIX" run-workflow
```

`run-workflow` exits `0` on a `SUCCEEDED` execution, `10` on any other
terminal state, and `11` if it times out waiting (`-t`/`--timeout`, default
3600s; `-p`/`--poll-interval` control the wait).

### Non-blocking submission

`cirrus manage "$RESOURCE_PREFIX" process` reads a payload from stdin and
enqueues it to the process SQS queue, returning immediately with the
`send_message` response — it doesn't wait for the workflow to run:

```bash
<cloudformation/workflows/minimal/payload.json.template cirrus payload template \
    -x id_suffix "-$(uuidgen)" \
    | cirrus manage "$RESOURCE_PREFIX" process
```

Use `process` when you want to submit and move on, tracking the execution
separately with the commands below — for example, submitting many payloads
in a batch without blocking on each one.

!!! note
    `run-workflow` validates the payload (via `CirrusPayload.validate`)
    before submitting it — a payload missing `process` or a `workflow`
    name, or with an `id` that doesn't match
    `<collections>/workflow-<workflow>/<itemids>`, is rejected client-side.
    `process` performs no client-side validation: it enqueues the payload
    as-is, and validation happens in the process Lambda, which routes an
    invalid payload to the payload bucket's invalid-payload prefix without
    starting a workflow.

## 2. Track state

### `get-state`

Once a payload has been claimed for processing, `get-state` returns its
state database record. If the record doesn't exist yet — for example,
immediately after a non-blocking `process` submission — the command retries
with backoff for up to 60 seconds before failing:

```bash
cirrus manage "$RESOURCE_PREFIX" get-state "collection/workflow-minimal/item-<uuid>"
```

This returns the raw DynamoDB item — see [State Database](../reference/state-database.md#fields)
for the full field reference. A record mid-processing looks like (illustrative
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

The current state is the prefix of `state_updated` (`PROCESSING` above). On
success, `outputs` (a list of output STAC item URLs) is added; on failure or
invalid input, `last_error` is added instead. `executions` accumulates one
ARN per claim, so a payload rerun with `replace=true` shows multiple entries.

### `get-execution` and `get-execution-events`

`get-execution` fetches Step Functions execution details
(`DescribeExecution`) either by ARN or by payload ID — pass one of
`--arn`/`--payload-id` (mutually exclusive, one required). With
`--payload-id`, the CLI resolves it to the execution's ARN via the state
database's `executions` list (most recent entry):

```bash
cirrus manage "$RESOURCE_PREFIX" get-execution --payload-id "collection/workflow-minimal/item-<uuid>"
```

`get-execution-events` fetches the full Step Functions event history the
same way (`--arn` or `--payload-id`), paginating through
`GetExecutionHistory`:

```bash
cirrus manage "$RESOURCE_PREFIX" get-execution-events --payload-id "collection/workflow-minimal/item-<uuid>"
```

Pass `--with-log-metadata` to inject parsed CloudWatch log metadata into
Lambda/Batch task succeed/fail events in the output.

`get-execution-input`/`get-execution-output` follow the same `--arn`/
`--payload-id` pattern and return just the execution's `input`/`output`
field (parsed from the Step Functions execution record, not the payload
bucket).

### Bulk queries

`query` filters state database records by `--collections-workflow`
(required), plus optional `--state`, `--since`, `--limit`, and
`--error-prefix`, streaming matches as newline-delimited JSON:

```bash
cirrus manage "$RESOURCE_PREFIX" query \
    --collections-workflow "collection_minimal" \
    --state SUCCEEDED \
    --since 1d
```

`--collections-workflow` takes the underscore-joined form
(`<collections>_<workflow>`, e.g. `collection_minimal` for this payload) —
see [State Database key schema](../reference/state-database.md#key-schema). `--state` accepts
one of `PROCESSING`, `SUCCEEDED`, `FAILED`, `INVALID`, `ABORTED`, `CLAIMED`.
`--since` takes an integer immediately followed by `d`, `h`, or `m` (e.g.
`7d`, `24h`, `30m`).

`get-input-payloads` takes the same filters plus `--rerun` (sets
`replace: true` on each returned payload) and streams the matching
**input payloads themselves**, fetched from the payload bucket, rather than
state database records.

### HTTP API equivalent

The same state is queryable over HTTP, unauthenticated, via API Gateway.
Given the collections/workflow summary route:

```bash
curl "https://<api-id>.execute-api.<region>.amazonaws.com/dev/collection/workflow-minimal"
```

and the single-item route for this payload:

```bash
curl "https://<api-id>.execute-api.<region>.amazonaws.com/dev/collection/workflow-minimal/item-<uuid>"
```

See [API Endpoints](../reference/http-api.md) for the full route list, query
parameters (`state`, `since`, `limit`, pagination via `nextkey`), and the
response shape — note the API's item responses go through `dbitem_to_item`,
which adds `payload_id`, `state`, `input_payload_url`, and
`output_payload_url` fields not present on the raw `get-state` output above.

## 3. Inspect output

Once the record's `state` is `SUCCEEDED`, fetch the output payload:

```bash
cirrus manage "$RESOURCE_PREFIX" get-output-payload "collection/workflow-minimal/item-<uuid>"
```

This resolves the payload ID's most recent execution, looks up its
`output_payload_url` in the state database, and downloads that object from
the payload bucket. `get-input-payload` works the same way for the
as-submitted payload. Both accept `-r`/`--raw` to print the payload
unformatted instead of pretty-printed JSON.

### Where these objects live

Per the [payload bucket key layout](../reference/payload-bucket.md#execution-payloads),
execution payloads are stored under:

```text
s3://<payload-bucket>/<root_prefix>/executions/<payload_id>/<execution_id>/input.json
s3://<payload-bucket>/<root_prefix>/executions/<payload_id>/<execution_id>/output.json
```

For this payload, with the default `CIRRUS_PAYLOAD_ROOT_PREFIX` (`cirrus`)
and the execution ARN's name component as `<execution_id>`:

```text
s3://<payload-bucket>/cirrus/executions/collection/workflow-minimal/item-<uuid>/<execution_id>/input.json
s3://<payload-bucket>/cirrus/executions/collection/workflow-minimal/item-<uuid>/<execution_id>/output.json
```

`<payload-bucket>` is the main stack's `CirrusPayloadBucket` output (see
[Quickstart: inspect deployed resources](quickstart.md#4-inspect-deployed-resources)).
`<execution_id>` is the Step Functions execution name, deterministically
derived from the payload ID and claim count — read it off the `executions`
entry in the state database record (or the ARN returned by
`get-execution`/`get-execution-events` above) rather than constructing it by
hand.

`output.json` is written only on successful completion; a `FAILED`,
`INVALID`, or `ABORTED` execution leaves only `input.json` under that
execution's prefix.
