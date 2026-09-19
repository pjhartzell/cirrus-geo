# Common workflows

Worked examples composing `cirrus` commands for routine operations. Every command's options are in the [Command reference](reference.md). The examples use a deployment named `name-dev`; substitute a name from `cirrus list-deployments`.

Commands that take a payload read it from standard input, so a payload comes in from a file with `<payload.json` and pipes from one command to the next.

## Run a workflow and wait for the result

```bash
<payload.json cirrus manage name-dev run-workflow
```

`run-workflow` validates the payload, enqueues it, and polls the state database every 15 seconds until the record leaves `PROCESSING`. Then it prints the output payload and exits with a code that scripts and smoke tests can check:

| Exit code | Meaning |
| --- | --- |
| `0` | `SUCCEEDED`; the output payload is printed |
| `10` | Any other terminal state; the record's `last_error` is printed |
| `11` | Still `PROCESSING` after `--timeout` seconds, default 3600 |

`--poll-interval` changes the polling period.

To enqueue without waiting:

```bash
<payload.json cirrus manage name-dev process
```

The two differ in where a bad payload is caught. `run-workflow` runs `CirrusPayload.validate` locally before submitting, so a payload missing `process`, missing a `workflow` name, or with a malformed `id` fails in the shell. It also requires the payload to have an `id`. `process` submits the payload as is, and validation happens in the `process` Lambda function, which sends a rejected payload to the payload bucket's invalid prefix without creating a state database record. The only trace is a [workflow event](../reference/workflow-events.md) and, after retries, a message on the dead-letter queue.

Both commands upload a payload larger than the SQS message limit to the payload bucket and enqueue a reference to it, so large payloads need no special handling.

## Inspect an execution

The execution commands take `--payload-id`, which resolves to the payload's most recent execution, or `--arn`:

```bash
cirrus manage name-dev get-execution --payload-id sentinel2/workflow-publish/S2A_1
cirrus manage name-dev get-execution --arn arn:aws:states:us-west-2:123456789012:execution:name-dev-publish:<execution-id>
```

From summary to event history to task logs:

```bash
cirrus manage name-dev get-execution-input --payload-id sentinel2/workflow-publish/S2A_1
cirrus manage name-dev get-execution-output --payload-id sentinel2/workflow-publish/S2A_1

# event history, with log group and request ID added to Lambda and Batch
# task events
cirrus manage name-dev get-execution-events --payload-id sentinel2/workflow-publish/S2A_1 --with-log-metadata

# the logs those events point at
cirrus manage name-dev get-lambda-logs /aws/lambda/name-dev-my-task <request-id>
cirrus manage name-dev get-batch-logs <log-stream-name>
```

Both log commands print 20 events by default and a `Next page token` line when there are more, to pass back as `--next-token`. `get-batch-logs` reads from `/aws/batch/job` unless `--log-group` says otherwise.

The state machine definition behind a workflow:

```bash
cirrus manage name-dev get-workflow-definition publish
```

## Check state and stored payloads

```bash
# the state database record, as stored
cirrus manage name-dev get-state sentinel2/workflow-publish/S2A_1

# the input and output payloads of the most recent execution
cirrus manage name-dev get-input-payload sentinel2/workflow-publish/S2A_1
cirrus manage name-dev get-output-payload sentinel2/workflow-publish/S2A_1
```

`get-state` retries with backoff for up to 60 seconds when the record does not exist yet, so it can be called immediately after `process`. `get-output-payload` fails for any record not in `SUCCEEDED`, since only a succeeded execution writes an output payload.

## Query the state database in bulk

`query` prints matching records, one JSON object per line. `--collections-workflow` is required, in the `<collections>_<workflow>` form of the table's partition key. `--state`, `--since`, `--limit` (at most 50,000), and `--error-prefix` narrow the result:

```bash
cirrus manage name-dev query --collections-workflow sentinel2_publish --state FAILED --since 1d
```

`--since` is an integer followed by `d`, `h`, or `m`. `--error-prefix` matches the start of `last_error`, which begins with the error type, so `--error-prefix stactask.exceptions.InvalidInput` selects one class of failure.

`get-input-payloads` takes the same filters and prints each matching record's input payload instead of the record:

```bash
cirrus manage name-dev get-input-payloads --collections-workflow sentinel2_publish --state FAILED --since 10d
```

## Rerun failed workflows in bulk

`get-input-payloads --rerun` sets `replace: true` on each payload's first process definition before printing it, so `process` will run it again even from a state it would otherwise skip. `process` takes one payload per invocation, so feed the lines through one at a time:

```bash
cirrus manage name-dev get-input-payloads \
    --collections-workflow sentinel2_publish --state FAILED --since 10d --rerun |
while IFS= read -r payload; do
    printf '%s' "$payload" | cirrus manage name-dev process
done
```

Which states rerun without `replace` and which need it is defined in [The replace field and reruns](../reference/payload-schema.md#the-replace-field-and-reruns).

## Invoke a Lambda function directly

`invoke-lambda` calls one of the deployment's functions synchronously with an event from standard input, bypassing the queue and Step Functions. Use the function's short name as `list-lambdas` prints it; the resource prefix is added for you.

```bash
cirrus manage name-dev list-lambdas
<payload.json cirrus manage name-dev invoke-lambda process
```

Invoking `process` this way runs the full intake on the payload and starts an execution, exactly as a queued message would, but the payload never touches the queue and a failure surfaces as the command's error output rather than on the dead-letter queue.

## Template payloads

Both templating commands substitute `$`-variables in a payload read from standard input, using Python's `string.Template` syntax with one extension: `${name?default}` supplies a default when the variable is unset. `cirrus payload template` uses only the variables given on the command line. `cirrus manage <deployment> template-payload` also loads the deployment's configuration values, so a template can reference `${CIRRUS_DATA_BUCKET}` and the like.

```bash
<payload-template.json cirrus payload template --var EXAMPLE_VAR value
<payload-template.json cirrus manage name-dev template-payload --var EXAMPLE_VAR value
```

Variables can also come from files of `NAME=value` lines passed as positional arguments. An unset variable without a default is an error unless `--silence-templating-errors` is given, in which case it is left as is.

## Validate a payload locally

```bash
<payload.json cirrus payload validate
<payload.json cirrus payload get-id
```

`validate` runs the same `CirrusPayload.validate` that `process` runs, and requires the payload to have an `id`. `get-id` prints the payload's `id`, generating one from the items and workflow name when it has none.

## Run local tools with deployment configuration

`exec` replaces the shell's process with the command; `call` runs it as a child and exits with its return code. Both first load the deployment's configuration values into the environment, which lets a local script or `cirrus.lib` session use the deployment's resources:

```bash
cirrus manage name-dev exec env | grep CIRRUS
cirrus manage name-dev call python my-script.py
```

## Migrate a pre-2.0 deployment

```bash
cirrus manage name-dev migrate --dry-run
cirrus manage name-dev migrate
```

See [Upgrading to 2.0](../operating/upgrading.md#running-the-migration) for what the migration changes.
