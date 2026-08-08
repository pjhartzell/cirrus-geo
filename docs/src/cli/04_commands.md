# Common CLI workflows

Worked examples composing `cirrus` commands for routine operational tasks.
For the full option listing of every command, see the
[CLI reference](reference.md). Examples use a deployment named `name-dev`;
substitute your own deployment name from `cirrus list-deployments`.

Commands that take a payload read it from stdin, so payloads pipe naturally
between commands and in from files with shell redirection (`<payload.json`).

## Run a workflow and wait for the result

Submit a payload, poll until the workflow reaches a terminal state, and print
the output payload:

``` bash
<payload.json cirrus manage name-dev run-workflow
```

`run-workflow` exits `0` on a `SUCCEEDED` execution, `10` on any other
terminal state, and `11` if it times out waiting (default 3600 seconds;
adjust with `--timeout`). The exit code makes it usable in scripts and CI
smoke tests.

To enqueue a payload without waiting, use `process` instead:

``` bash
<payload.json cirrus manage name-dev process
```

Payloads larger than the SQS maximum message size are uploaded to the payload
bucket automatically and enqueued by reference, so oversized payloads need no
special handling.

## Inspect an execution

Most execution commands accept either `--payload-id` or `--arn` to identify
the execution:

``` bash
cirrus manage name-dev get-execution --payload-id sar/workflow-test/example-01
cirrus manage name-dev get-execution --arn arn:aws:states:us-west-2:000000000011:execution:fd-name-dev-cirrus-project:c123456789-b19292-999
```

Walk an execution from summary to event history to task logs:

``` bash
# input and output payloads for the execution
cirrus manage name-dev get-execution-input --payload-id sar/workflow-test/example-01
cirrus manage name-dev get-execution-output --payload-id sar/workflow-test/example-01

# event history, with log-group/request-id metadata injected into
# task succeed/fail events for follow-up log queries
cirrus manage name-dev get-execution-events --payload-id sar/workflow-test/example-01 --with-log-metadata

# fetch the logs a task event pointed at
cirrus manage name-dev get-lambda-logs /aws/lambda/my-function abc123-request-id
cirrus manage name-dev get-batch-logs my-job-log-stream
```

The state machine definition backing a workflow is available by workflow
name:

``` bash
cirrus manage name-dev get-workflow-definition my-workflow
```

## Check state and stored payloads

``` bash
# state database record for a payload ID
cirrus manage name-dev get-state sar/workflow-test/example-01

# input/output payloads as stored in the payload bucket
cirrus manage name-dev get-input-payload sar/workflow-test/example-01
cirrus manage name-dev get-output-payload sar/workflow-test/example-01
```

## Query the state database in bulk

`query` returns state database records as NDJSON, filtered by
`--collections-workflow` (required) plus optional `--state`, `--since`,
`--limit`, and `--error-prefix`:

``` bash
cirrus manage name-dev query --collections-workflow "sar-test_workflow" --state FAILED --since 1d
```

`get-input-payloads` takes the same filters but resolves each matching record
to its input payload from S3:

``` bash
cirrus manage name-dev get-input-payloads --collections-workflow "sar-test_workflow" --state FAILED --since 10d
```

## Rerun failed workflows in bulk

`get-input-payloads --rerun` alters each returned payload so it can be
resubmitted. The output is NDJSON — one payload per line — and `process`
enqueues one payload per invocation, so submit line by line:

``` bash
cirrus manage name-dev get-input-payloads \
    --collections-workflow "sar-test_workflow" --state FAILED --since 10d --rerun |
while IFS= read -r payload; do
    printf '%s' "$payload" | cirrus manage name-dev process
done
```

See the [monitoring guide](../cirrus/80_monitoring.md#rerun-tasks) for which
states rerun under which conditions.

## Template payloads

Both templating commands substitute `$`-prefixed variables in a payload read
from stdin. `cirrus payload template` uses only the variables you supply;
`cirrus manage ... template-payload` additionally loads the deployment's
environment variables:

``` bash
<payload-template.json cirrus payload template --var EXAMPLE_VAR value
<payload-template.json cirrus manage name-dev template-payload --var EXAMPLE_VAR value
```

## Validate a payload locally

``` bash
# check that a payload is a valid Cirrus process payload
<payload.json cirrus payload validate

# show the ID a payload would get (or has)
<payload.json cirrus payload get-id
```

## Run local tools with deployment environment variables

`exec` replaces the current process; `call` runs the command in a child
process. Both load the deployment's environment variables first, which is
useful for running local scripts or debugging tools against a deployment's
resources:

``` bash
cirrus manage name-dev exec env | grep CIRRUS
cirrus manage name-dev call bash my-script.sh
```

## Migrate a pre-2.0 deployment

Preview, then apply, the v2 state database and payload bucket migration:

``` bash
cirrus manage name-dev migrate --dry-run
cirrus manage name-dev migrate
```

See [Upgrading to 2.0](../cirrus/85_upgrading.md) for what the migration
changes and its options.
