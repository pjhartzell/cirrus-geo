# Quickstart

This runs Cirrus on [LocalStack](https://www.localstack.cloud/) in a Docker container and submits two payloads through it, one that succeeds and one that fails. It needs no AWS account. The same CloudFormation templates deploy to AWS; that procedure is on [Deploying to AWS](../operating/deploying.md).

## Prerequisites

- Docker, to run LocalStack.
- The AWS CLI. The provisioning script drives LocalStack through it.
- [uv](https://docs.astral.sh/uv/), which the Lambda packaging script uses to build the function distribution from `uv.lock`.
- A clone of the [cirrus-geo repository](https://github.com/cirrus-geo/cirrus-geo), since the templates, scripts, and lock file live there.
- The Cirrus CLI: `pipx install 'cirrus-geo[cli]'` or `uv tool install 'cirrus-geo[cli]'`. See [Installing](../cli/using-the-cli.md#installing).

## 1. Configure and start LocalStack

From the repository root:

```bash
cp .env.localstack.example .env.localstack
source .env.localstack

docker compose up -d -V
```

`.env.localstack` points the AWS CLI at `http://localhost:4566` with placeholder credentials, sets the stack names and the `RESOURCE_PREFIX` (`cirrus-sandbox`), and sets `_USING_LOCALSTACK_CONFIG=true`, which the provisioning script requires before it will run. The placeholder credentials are a guard: nothing in this guide can reach a real AWS account. `docker compose up` starts LocalStack from `compose.yml` at the repository root.

## 2. Deploy

```bash
./bin/localstack-provision.bash bootstrap
./bin/localstack-provision.bash deploy
```

`bootstrap` creates the stack holding the artifacts bucket. `deploy` packages the Lambda functions, packages and deploys the main stack with `EnableVpc=false`, and deploys the `minimal` workflow stack from `cloudformation/workflows/minimal/`. It can be rerun to apply changes.

!!! note
    LocalStack can be left in a broken state by a failed CloudFormation apply or rollback. If a later step cannot recover, restart it with `docker compose up -d -V` and redeploy from `bootstrap`.

The deployment is now visible to the Cirrus CLI, which reads the LocalStack endpoint from the sourced environment:

```bash
cirrus list-deployments
```

## 3. Run the test payloads

The `minimal` workflow is a single `Choice` state that succeeds when the payload's `process[0].succeed` field is `true` and fails otherwise. The script's `test` command submits one payload of each kind and checks the exit codes:

```bash
./bin/localstack-provision.bash test
```

To submit one yourself, render the workflow's payload template and pass it to `run-workflow`, which submits it, polls the state database until the execution finishes, and prints the output payload:

```bash
<cloudformation/workflows/minimal/payload.json.template cirrus payload template \
    -x id_suffix "-$(uuidgen)" \
    | cirrus manage "$RESOURCE_PREFIX" run-workflow
```

The template has three variables: `succeed`, default `true`, `replace`, default `false`, and `id_suffix`, default empty. A unique `id_suffix` gives each submission a new payload ID. Set `succeed` to `false` for a failing execution, which `run-workflow` reports with exit code `10`:

```bash
<cloudformation/workflows/minimal/payload.json.template cirrus payload template \
    -x id_suffix "-$(uuidgen)" \
    -x succeed false \
    | cirrus manage "$RESOURCE_PREFIX" run-workflow
```

Resubmitting a payload ID that already succeeded is skipped unless `replace` is `true`. See [The replace field and reruns](../reference/payload-schema.md#the-replace-field-and-reruns).

## 4. Look around

The state database record for the last payload, by its ID:

```bash
cirrus manage "$RESOURCE_PREFIX" get-state "collection/workflow-minimal/item-<uuid>"
```

The HTTP API is reachable through LocalStack's API Gateway emulation. Get the API ID from the main stack's outputs, then request a path:

```bash
API_ID=$(aws cloudformation describe-stacks \
  --stack-name "$MAIN_STACK" \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayId`].OutputValue' \
  --output text)

curl "http://localhost:4566/restapis/${API_ID}/dev/_user_request_/collection/workflow-minimal/items"
```

[Your first pipeline](first-pipeline.md) continues from here by adding a workflow and task of your own.

## 5. Tear down

```bash
./bin/localstack-provision.bash delete
./bin/localstack-provision.bash debootstrap
docker compose down
```

`delete` removes the workflow and main stacks after emptying the buckets; `debootstrap` removes the bootstrap stack.

## Next steps

- [Your first pipeline](first-pipeline.md) to add a workflow with a task of your own to this deployment.
- [Deploying to AWS](../operating/deploying.md) for the same templates in a real account.
- [Common workflows](../cli/common-workflows.md) for the rest of the command set.
