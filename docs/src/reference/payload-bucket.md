# Payload bucket

The payload bucket is the S3 bucket where Cirrus stores payload JSON: the input and output of every execution, and transient copies of payloads that are too large to pass inline or that failed validation. Together with the [state database](state-database.md) it is the record of a deployment's work. The state database says what state a payload is in; the bucket holds the payloads themselves.

## Configuration

All bucket access goes through `PayloadBucket` in `cirrus.lib.payload_bucket`. `PayloadBucket.from_env` reads the bucket name from `CIRRUS_PAYLOAD_BUCKET` and the root prefix from `CIRRUS_PAYLOAD_ROOT_PREFIX`, default `cirrus`. It raises `UndefinedPayloadBucketError` when the bucket name is unset. Any bucket the functions can read and write serves. `cloudformation/core/base.yaml` creates `${ResourcePrefix}-payload-<account-id>` and sets both variables on the functions, but a deployment built with other tooling can point them anywhere.

Every key Cirrus writes is under the root prefix, so the bucket can be shared with other content, or with a second Cirrus deployment using a different prefix, without key collisions.

## Key layout

Keys are split by how long the object needs to live:

- `<root>/tmp/` holds transient objects that are not needed once processing has moved on. A lifecycle rule is expected to expire them.
- `<root>/executions/` holds each execution's input and output payload, which the CLI and HTTP API resolve from state database records and which nothing expires.

```text
s3://<payload-bucket>/
└── cirrus/                               # CIRRUS_PAYLOAD_ROOT_PREFIX
    ├── tmp/
    │   ├── oversized/<uuid>.json         # payloads too large to pass inline
    │   ├── batch/<payload_id>/<uuid>.json
    │   │                                 # input to a Batch job, written by pre-batch;
    │   │                                 # the job writes <uuid>_out.json beside it
    │   └── invalid/<uuid>.json           # messages process rejected
    └── executions/<payload_id>/<execution_id>/
        ├── input.json                    # written by process on claim
        └── output.json                   # written by update-state on success
```

The prefixes are attributes of `PayloadBucket`, computed from the root prefix at construction. Code that needs a key should call the class rather than build one.

A payload ID contains slashes, so keys under `executions/` and `tmp/batch/` fan out into several levels of S3 prefix, which makes every execution for a collection, workflow, or item set listable with an ordinary prefix query.

### Execution payloads

`process` writes the input payload to `executions/<payload_id>/<execution_id>/input.json` after claiming the payload and before starting the execution. If the payload arrived as a `{"url": ...}` reference, the referenced object is fetched and its content written, so the execution's input is always stored under this key. `update-state` writes the output payload to `output.json` beside it when the execution succeeds. A `FAILED`, `INVALID`, or `ABORTED` execution leaves only `input.json`.

`<execution_id>` is the Step Functions execution name, a UUID5 that `PayloadManagers.gen_execution_arn` derives from the payload ID and the record's existing `executions` list. Because a payload can run more than once, one payload ID prefix can hold several execution directories, one per attempt.

The state database record's `executions` list plus the payload ID is therefore enough to locate both files for any attempt. `StateDB.dbitem_to_item` fills `input_payload_url` and `output_payload_url` this way from the most recent execution, and the CLI's `get-input-payload` and `get-output-payload` commands download those URLs.

### Oversized payloads

Cirrus passes payloads inline through Step Functions and EventBridge, and EventBridge embeds an execution's input and output as escaped strings inside its event. To stay under that limit, `PayloadManager.get_payload` compares the JSON-escaped length of a payload with `MAX_PAYLOAD_LENGTH`, 120,000 bytes in `cirrus.lib.payload_manager`, and when the payload is larger uploads it to `tmp/oversized/<uuid>.json` and returns `{"url": "s3://..."}` in its place. This happens in `process` when starting an execution and in `post-batch` when returning a Batch task's output.

The reference is resolved wherever a payload is read: `process` at intake, `CirrusPayload.from_event` in the other functions, and stac-task's `Task.handler` in a task. A Lambda task with its own handler must resolve it itself. The Cirrus CLI's `process` and `run-workflow` commands also upload a payload larger than the SQS message limit to this prefix and enqueue a reference.

### Batch payloads

`pre-batch` writes the state input to `tmp/batch/<payload_id>/<uuid>.json` and returns that URL as `url` together with `url_out`, the same key with `_out.json` in place of `.json`, where the Batch job writes its output. The `<payload_id>/<uuid>.json` form, rather than `<uuid>/input.json`, is kept for compatibility with earlier versions.

### Invalid payloads

When `process` cannot parse a message or the payload fails validation, it uploads the raw message to `tmp/invalid/<uuid>.json` and puts that URL on the [workflow event](workflow-events.md) it emits. This is diagnostic storage, expected to expire with the rest of `tmp/`. A deployment that needs to keep rejected inputs should copy them elsewhere from a subscriber to the workflow event topic.

## Lifecycle and retention

The bucket the base stack creates has one lifecycle rule: objects under `<root>/tmp/` expire after 10 days. That is long enough for a payload to survive retries and a manual rerun. An operator supplying their own bucket should add the same rule. Shortening it risks expiring an object an in-flight retry still needs. Widening it to cover `executions/` deletes execution history, which breaks `get-input-payload` and `get-output-payload` for those executions.

Nothing Cirrus-managed expires `executions/`. A deployment that wants to bound its growth can add its own rule on that prefix, knowing that any execution whose payloads expire becomes unreadable through the CLI and API even though its state database record remains.

## Who reads and writes

| Caller | Writes | Reads |
| --- | --- | --- |
| `process` | `executions/.../input.json`, `tmp/oversized/`, `tmp/invalid/` | `{"url": ...}` references from any bucket |
| `update-state` | `executions/.../output.json` | Nothing; payloads come from the EventBridge event |
| `pre-batch` | `tmp/batch/` | |
| `post-batch` | `tmp/oversized/` when the output is large | `tmp/batch/..._out.json` |
| Tasks | `tmp/batch/..._out.json` from a Batch job | `tmp/oversized/` and `tmp/batch/` |
| Cirrus CLI | `tmp/oversized/` when enqueuing a large payload | `executions/` via state database records |
