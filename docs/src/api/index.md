# Python library

The `cirrus-geo` distribution installs the `cirrus` package, which has two parts. `cirrus.lib` is the library the five framework Lambda functions are built on: the payload model, the state database and payload bucket clients, workflow events, and logging. `cirrus.management` is the layer under the Cirrus CLI and needs the `cli` extra (`pip install 'cirrus-geo[cli]'`).

Tasks mostly do not import either. A task is built on [stac-task](https://github.com/stac-utils/stac-task), and its only coupling to Cirrus is the payload it receives and returns. The places user code does reach for `cirrus`:

| Need | Import | Notes |
| --- | --- | --- |
| Build or validate a payload in a feeder | `cirrus.lib.cirrus_payload.CirrusPayload` | `CirrusPayload(payload).validate()` is the check `process` runs. `set_id()` generates the `id` the same way. See [CirrusPayload](cirrus_payload.md) |
| JSON logs carrying the payload ID in a task | `cirrus.lib.logging.CirrusLoggerAdapter` | See [Structured logging](../building-pipelines/tasks.md#structured-logging) |
| Read state records or execution payloads from a script | `cirrus.lib.statedb.StateDB`, `cirrus.lib.payload_bucket.PayloadBucket` | Both read their configuration from `CIRRUS_*` environment variables, which `cirrus manage <deployment> exec` and `call` load for you. See [StateDB](statedb.md) and [PayloadBucket](payload_bucket.md) |
| Parse messages from the workflow event topic | `cirrus.lib.events.WorkflowEvent` | `WorkflowEvent.from_message_str(body)` rebuilds the event from an SNS message body. See [Events](events.md) |
| Do what the CLI does, from Python | `cirrus.management.deployment.Deployment` | `Deployment.from_name(name, session)` resolves a deployment from Parameter Store and exposes `enqueue_payload`, `run_workflow`, `get_payload_state`, `fetch_payload`, and the rest. See [Deployment class](deployment.md) |

Exceptions the library raises, and the CLI's exit-code carrying `CirrusError`, are on [Errors and exceptions](errors.md).

The reference pages that follow are generated from the source docstrings.
