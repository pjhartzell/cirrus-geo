# Deploying to AWS

This is the procedure for deploying the CloudFormation templates in [`cloudformation/`](https://github.com/cirrus-geo/cirrus-geo/tree/main/cloudformation) to an AWS account, updating them, and removing them. What the templates create, every parameter, and what a deployment built with other tooling must provide are on [Deployment contract](../reference/deployment-contract.md). Concurrency and quotas are on [Scaling and quotas](scaling.md).

## Prerequisites

- The AWS CLI, with credentials that can create every resource type in the [contract](../reference/deployment-contract.md#resources) and named IAM roles.
- [uv](https://docs.astral.sh/uv/), which the packaging script uses to build the Lambda distribution from `uv.lock`.
- A clone of the [cirrus-geo repository](https://github.com/cirrus-geo/cirrus-geo).
- The Cirrus CLI, to submit a test payload at the end. See [Installing](../cli/using-the-cli.md#installing).

## Configure

Stack names and parameters come from shell variables. Copy the example file, edit it, and source it:

```bash
cp .env.aws.example .env.aws
# edit .env.aws
source .env.aws
```

| Variable | Default | Sets |
| --- | --- | --- |
| `BOOTSTRAP_STACK` | `cirrus-bootstrap` | Bootstrap stack name |
| `MAIN_STACK` | `cirrus-sandbox` | Main stack name |
| `MINIMAL_WORKFLOW_STACK` | `cirrus-sandbox-minimal-workflow` | Stack name for the `minimal` workflow |
| `RESOURCE_PREFIX` | `cirrus-sandbox` | The `ResourcePrefix` parameter, from which every resource name derives |
| `LAMBDA_PYTHON_VERSION` | `3.13` | The `LambdaPythonVersion` parameter and the packaging target |
| `LAMBDA_ARCH` | `arm64` | The `LambdaArch` parameter and the packaging target |
| `LOG_LEVEL` | `DEBUG` | The `LogLevel` parameter |
| `ENABLE_VPC` | `true` | The `EnableVpc` parameter |
| `VPC_CIDR`, `PRIVATE_SUBNET_CIDR`, `PUBLIC_SUBNET_CIDR` | `10.1.0.0/16`, `10.1.10.0/24`, `10.1.1.0/24` | The VPC parameters, used when `ENABLE_VPC` is `true` |

The parameters are described under [Main stack parameters](../reference/deployment-contract.md#main-stack-parameters). Set `ENABLE_VPC="false"` unless a function must reach something only reachable from inside a VPC; the NAT gateway the VPC stack creates is billed hourly regardless of traffic. `RESOURCE_PREFIX` is also the deployment name the Cirrus CLI uses.

## 1. Deploy the bootstrap stack

The bootstrap stack creates the bucket that packaged Lambda code and nested templates are uploaded to:

```bash
aws cloudformation deploy \
  --stack-name "$BOOTSTRAP_STACK" \
  --template-file cloudformation/bootstrap/bootstrap.yaml \
  --parameter-overrides \
    "ResourcePrefix=$RESOURCE_PREFIX"
```

`aws cloudformation deploy` creates the stack or updates it if it exists. That holds for every deploy command on this page.

## 2. Package the Lambda functions

```bash
./bin/build-lambda-dist.py \
    -p "$LAMBDA_PYTHON_VERSION" \
    -a "$LAMBDA_ARCH" \
    -o "cloudformation/core/lambda-packages/cirrus-lambda-dist.zip"
```

The script creates a virtual environment for the target Python version, runs `uv sync --locked` against `uv.lock` for the target platform, and zips the resulting site-packages with the function handlers. The main stack's function resources reference that zip path.

## 3. Package and deploy the main stack

```bash
ARTIFACT_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name "$BOOTSTRAP_STACK" \
  --query 'Stacks[0].Outputs[?OutputKey==`CirrusDeploymentArtifactsBucket`].OutputValue' \
  --output text)

aws cloudformation package \
  --template-file cloudformation/main.yaml \
  --s3-bucket "$ARTIFACT_BUCKET" \
  --output-template-file packaged-template.yaml

aws cloudformation deploy \
  --stack-name "$MAIN_STACK" \
  --template-file packaged-template.yaml \
  --parameter-overrides \
    "ResourcePrefix=$RESOURCE_PREFIX" \
    "LambdaPythonVersion=$LAMBDA_PYTHON_VERSION" \
    "LambdaArch=$LAMBDA_ARCH" \
    "LogLevel=$LOG_LEVEL" \
    "EnableVpc=$ENABLE_VPC" \
    "VpcCidr=$VPC_CIDR" \
    "PrivateSubnetCidr=$PRIVATE_SUBNET_CIDR" \
    "PublicSubnetCidr=$PUBLIC_SUBNET_CIDR" \
  --capabilities CAPABILITY_NAMED_IAM
```

`package` uploads the Lambda zip and the nested templates to the artifacts bucket and writes a template with those locations substituted. `CAPABILITY_NAMED_IAM` is required because the stack creates named IAM roles. The deploy waits on every nested stack, which takes several minutes.

## 4. Verify

```bash
aws cloudformation describe-stacks --stack-name "$MAIN_STACK" \
  --query 'Stacks[0].Outputs | sort_by(@, &Description)' \
  --output table

cirrus list-deployments
cirrus manage "$RESOURCE_PREFIX" show
```

The outputs include the bucket names, the state table, the process queue URL, the topic ARNs, the API Gateway URL, and the Parameter Store prefix. `list-deployments` shows `RESOURCE_PREFIX` once the CLI stack's parameters exist, and `show` prints the configuration the CLI resolved from them.

## 5. Deploy a workflow stack

Each workflow is its own stack, deployed after the main stack and coupled to it only by `ResourcePrefix`. The in-repo `minimal` workflow is the smallest complete one:

```bash
aws cloudformation deploy \
  --template-file cloudformation/workflows/minimal/state_machine.yaml \
  --stack-name "$MINIMAL_WORKFLOW_STACK" \
  --parameter-overrides \
    "ResourcePrefix=$RESOURCE_PREFIX" \
  --capabilities CAPABILITY_NAMED_IAM
```

A workflow of your own deploys the same way with its own template. See [Defining a workflow](../building-pipelines/workflows.md).

## 6. Submit a test payload

```bash
<cloudformation/workflows/minimal/payload.json.template cirrus payload template \
    -x id_suffix "-$(uuidgen)" \
    | cirrus manage "$RESOURCE_PREFIX" run-workflow
```

`run-workflow` exits `0` when the execution succeeds. The template's `succeed` variable, set with `-x succeed false`, drives a failing execution. See [Run a workflow and wait for the result](../cli/common-workflows.md#run-a-workflow-and-wait-for-the-result).

## Updating

- **Cirrus code or templates**: repeat steps 2 and 3. `package` uploads a new zip and `deploy` updates the stack in place, including the function code.
- **A workflow**: repeat step 5 for that workflow's stack. Executions already running continue on the old definition.
- **Parameters**: change the value in `.env.aws`, source it, and repeat step 3. `ResourcePrefix` cannot be changed in place, since every resource name derives from it; a new prefix is a new deployment.

Updating a Batch task's resources has failure modes of its own. See [Updating Batch resources](updating-batch-resources.md).

## Deleting

CloudFormation will not delete a bucket with objects in it, so empty the three buckets first:

```bash
DATA_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name "$MAIN_STACK" \
  --query 'Stacks[0].Outputs[?OutputKey==`CirrusDataBucket`].OutputValue' \
  --output text)

PAYLOAD_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name "$MAIN_STACK" \
  --query 'Stacks[0].Outputs[?OutputKey==`CirrusPayloadBucket`].OutputValue' \
  --output text)

ARTIFACT_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name "$BOOTSTRAP_STACK" \
  --query 'Stacks[0].Outputs[?OutputKey==`CirrusDeploymentArtifactsBucket`].OutputValue' \
  --output text)

aws s3 rm "s3://$DATA_BUCKET" --recursive
aws s3 rm "s3://$PAYLOAD_BUCKET" --recursive
aws s3 rm "s3://$ARTIFACT_BUCKET" --recursive
```

Then delete the stacks: every workflow stack first, then the main stack, then the bootstrap stack.

```bash
aws cloudformation delete-stack --stack-name "$MINIMAL_WORKFLOW_STACK"
aws cloudformation wait stack-delete-complete --stack-name "$MINIMAL_WORKFLOW_STACK"

aws cloudformation delete-stack --stack-name "$MAIN_STACK"
aws cloudformation wait stack-delete-complete --stack-name "$MAIN_STACK"

aws cloudformation delete-stack --stack-name "$BOOTSTRAP_STACK"
aws cloudformation wait stack-delete-complete --stack-name "$BOOTSTRAP_STACK"
```

Deleting the main stack deletes the state table and the payload bucket, and with them the record of every execution.
