# Quickstart

This runs Cirrus on [LocalStack](https://www.localstack.cloud/) in a Docker container and submits two payloads through it, one that succeeds and one that fails. It needs no AWS account. The deployment is the core stack plus one test workflow, created by the same CloudFormation templates used to [deploy to AWS](../operating/deploying.md).

## Prerequisites

- Docker, to run LocalStack.
- The AWS CLI. The provisioning script is a set of `aws cloudformation` and `aws s3` calls, and the environment file in step 1 points them at LocalStack instead of AWS.
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

`.env.localstack` sets the variables every later command reads. It points the AWS CLI and the Cirrus CLI at `http://localhost:4566` with placeholder credentials, names the three CloudFormation stacks, sets the `RESOURCE_PREFIX` (`cirrus-sandbox`) that starts every resource name, and sets `_USING_LOCALSTACK_CONFIG=true`, which the provisioning script requires before it will run. Source it again in each new shell. The placeholder credentials are a guard: the provisioning script hard-codes the same values, so nothing in this guide can reach a real AWS account.

`docker compose up` starts LocalStack from `compose.yml` at the repository root. The `-V` flag recreates anonymous volumes instead of reusing a previous container's, so a restart with the same command begins from empty state.

## 2. Deploy

```bash
./bin/localstack-provision.bash bootstrap
./bin/localstack-provision.bash deploy
```

`bootstrap` creates a stack holding one S3 bucket for deployment artifacts. `deploy` runs three steps:

- Builds the Lambda function distribution as a zip file, using uv and `uv.lock`.
- Packages the main template, which uploads the zip and the nested stack templates to the artifacts bucket, then deploys the main stack with `EnableVpc=false`.
- Deploys the `minimal` workflow stack from `cloudformation/workflows/minimal/`.

`bootstrap` runs once. Rerun `deploy` to apply template or Lambda code changes to the existing stacks.

!!! note
    LocalStack can be left in a broken state by a failed CloudFormation apply or rollback. If a later step cannot recover, restart it with `docker compose up -d -V` and redeploy from `bootstrap`.

The main stack registers the deployment in Parameter Store under `/cirrus/deployments/`, which is where the Cirrus CLI looks for deployments. The CLI reaches LocalStack through the same sourced environment as the AWS CLI, so this lists `cirrus-sandbox`:

```bash
cirrus list-deployments
```

## 3. Run the test payloads

The `minimal` workflow is a single `Choice` state that succeeds when the payload's `process[0].succeed` field is `true` and fails otherwise. The script's `test` command submits one payload of each kind and checks that the first exits `0` and the second exits `10`:

```bash
./bin/localstack-provision.bash test
```

To submit one yourself, render the workflow's payload template and pipe the result to `run-workflow`. `payload template` reads the template from stdin and substitutes each variable given with `-x`. `run-workflow` reads the rendered payload from stdin, submits it, polls the state database until the execution leaves PROCESSING, and prints the output payload:

```bash
<cloudformation/workflows/minimal/payload.json.template cirrus payload template \
    -x id_suffix "-$(uuidgen)" \
    | cirrus manage "$RESOURCE_PREFIX" run-workflow
```

The template has three variables: `succeed`, default `true`, `replace`, default `false`, and `id_suffix`, default empty. A unique `id_suffix` gives each submission a new payload ID. Set `succeed` to `false` for a failing execution, which `run-workflow` reports with exit code `10` and a `last_error` field in place of the output payload:

```bash
<cloudformation/workflows/minimal/payload.json.template cirrus payload template \
    -x id_suffix "-$(uuidgen)" \
    -x succeed false \
    | cirrus manage "$RESOURCE_PREFIX" run-workflow
```

`run-workflow` polls every 15 seconds by default, so expect a short wait before it returns. You can append `-p 1` to the end of the command to poll every second.

Resubmitting a payload ID that already succeeded is skipped unless `replace` is `true`. See [The replace field and reruns](../reference/payload-schema.md#the-replace-field-and-reruns).

## 4. Look around

`get-state` prints the state database record for a payload ID. For the last payload submitted above, substitute the UUID you generated:

```bash
cirrus manage "$RESOURCE_PREFIX" get-state "collection/workflow-minimal/item-<uuid>"
```

The record holds the state, the created and updated timestamps, the ARNs of the payload's executions, and for a failed payload the `last_error`.

The HTTP API is reachable through LocalStack's API Gateway emulation at a LocalStack-specific URL: `/restapis/<API ID>/<stage>/_user_request_/` followed by the path the API would serve in AWS. The stage is `dev`. Get the API ID from the main stack's outputs, then request the item list for the collection and workflow:

```bash
API_ID=$(aws cloudformation describe-stacks \
  --stack-name "$MAIN_STACK" \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayId`].OutputValue' \
  --output text)

curl "http://localhost:4566/restapis/${API_ID}/dev/_user_request_/collection/workflow-minimal/items"
```

The response lists the state record of every payload whose ID starts with `collection/workflow-minimal`. Drop the trailing `/items` to get counts by state instead.

[Your first pipeline](first-pipeline.md) continues from here by adding a workflow and task of your own.

## 5. Tear down

```bash
./bin/localstack-provision.bash delete
./bin/localstack-provision.bash debootstrap
docker compose down
```

`delete` removes the workflow stack, empties the data and payload buckets, and removes the main stack. `debootstrap` empties the artifacts bucket and removes the bootstrap stack. The buckets are emptied first because CloudFormation will not delete a bucket that still holds objects.

## Next steps

- [Your first pipeline](first-pipeline.md) to add a workflow with a task of your own to this deployment.
- [Deploying to AWS](../operating/deploying.md) for the same templates in a real account.
- [Common workflows](../cli/common-workflows.md) for the rest of the command set.
