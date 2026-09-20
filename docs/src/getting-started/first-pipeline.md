# Your first pipeline

This adds a workflow with one Lambda task of your own to a running deployment, submits a payload through it, and reads back what happened. It works against the [Quickstart](quickstart.md) deployment on LocalStack or a deployment made with [Deploying to AWS](../operating/deploying.md); the commands are the same once the matching environment file is sourced.

The task is deliberately small. It takes the payload, stamps each item with the time it ran, and returns the payload. That is enough to show the pieces a real pipeline is built from and where each one is documented.

## 1. The task and the workflow

Save the following as `hello-workflow.yaml`. It is one CloudFormation template holding the task, as a Lambda function with its code inline, the workflow, as a Step Functions state machine, and the two roles they run under.

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: 'Cirrus tutorial - hello workflow with one Lambda task'

Parameters:
  ResourcePrefix:
    Type: String
    Description: Prefix for all resource names
  LambdaPythonVersion:
    Type: String
    Description: Python version for the task function, for example 3.13

Resources:
  HelloTaskRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: !Sub '${ResourcePrefix}-hello-task-role'
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: lambda.amazonaws.com
            Action: sts:AssumeRole
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

  HelloTask:
    Type: AWS::Lambda::Function
    Properties:
      FunctionName: !Sub '${ResourcePrefix}-hello-task'
      Runtime: !Sub 'python${LambdaPythonVersion}'
      Handler: index.handler
      Role: !GetAtt HelloTaskRole.Arn
      Timeout: 30
      Code:
        ZipFile: |
          from datetime import UTC, datetime


          def handler(payload, context):
              stamp = datetime.now(UTC).isoformat()
              for item in payload["features"]:
                  item.setdefault("properties", {})["tutorial:processed"] = stamp
              return payload

  HelloWorkflowRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: !Sub '${ResourcePrefix}-hello-workflow-role'
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: states.amazonaws.com
            Action: sts:AssumeRole
      Policies:
        - PolicyName: InvokeHelloTask
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action: lambda:InvokeFunction
                Resource: !GetAtt HelloTask.Arn

  HelloWorkflow:
    Type: AWS::StepFunctions::StateMachine
    Properties:
      StateMachineName: !Sub '${ResourcePrefix}-hello'
      RoleArn: !GetAtt HelloWorkflowRole.Arn
      DefinitionString: !Sub |
        {
          "Comment": "Tutorial workflow with one Lambda task",
          "StartAt": "hello-task",
          "States": {
            "hello-task": {
              "Type": "Task",
              "Resource": "arn:aws:states:::lambda:invoke",
              "Parameters": {
                "FunctionName": "${HelloTask.Arn}",
                "Payload.$": "$"
              },
              "OutputPath": "$.Payload",
              "End": true,
              "Retry": [
                {
                  "ErrorEquals": ["Lambda.TooManyRequestsException", "Lambda.Unknown"],
                  "IntervalSeconds": 1,
                  "BackoffRate": 2,
                  "MaxAttempts": 5
                }
              ],
              "Catch": [
                {
                  "ErrorEquals": ["States.ALL"],
                  "ResultPath": "$.error",
                  "Next": "failure"
                }
              ]
            },
            "failure": {
              "Type": "Fail",
              "ErrorPath": "$.error.Error",
              "CausePath": "$.error.Cause"
            }
          }
        }
```

Four things in it are Cirrus conventions rather than choices:

- **The state machine name**, `${ResourcePrefix}-hello`. `process` finds a workflow by prepending the prefix to the `workflow` name in the payload, and `update-state` is only invoked for state machines with that prefix. See [Naming and dispatch](../building-pipelines/workflows.md#naming-and-dispatch).
- **`"OutputPath": "$.Payload"`** on the task state. The `lambda:invoke` integration wraps the function's return value, and `update-state` needs the execution's output to be the payload itself.
- **The `Catch` and `Fail` pair.** The task's error is stored under `$.error` and the `Fail` state reads it back with `ErrorPath` and `CausePath`, which is how the error reaches the state database. See [Capturing errors](../building-pipelines/workflows.md#capturing-errors).
- **The handler's contract**: a payload in, a payload out, with `features` holding the output items. Everything else about the function is ordinary Lambda.

## 2. Deploy it

The workflow stack needs the same `ResourcePrefix` as the core stack, which is in the sourced environment file as `RESOURCE_PREFIX`:

```bash
aws cloudformation deploy \
  --template-file hello-workflow.yaml \
  --stack-name "$RESOURCE_PREFIX-hello-workflow" \
  --parameter-overrides \
    "ResourcePrefix=$RESOURCE_PREFIX" \
    "LambdaPythonVersion=$LAMBDA_PYTHON_VERSION" \
  --capabilities CAPABILITY_NAMED_IAM
```

Nothing in the core stack changes. The only link between the two stacks is the name.

## 3. Submit a payload

Save this as `payload.json`:

```json
{
    "type": "FeatureCollection",
    "id": "tutorial/workflow-hello/item-1",
    "features": [
        {
            "id": "item-1",
            "collection": "tutorial",
            "properties": {}
        }
    ],
    "process": [
        {
            "workflow": "hello"
        }
    ]
}
```

The `id` follows `<collections>/workflow-<workflow>/<itemids>`, and `process[0].workflow` is `hello`, the part of the state machine name after the prefix. The item is a stub with only an `id` and a `collection`, which is all Cirrus requires of an item. See [Payload schema](../reference/payload-schema.md).

```bash
<payload.json cirrus manage "$RESOURCE_PREFIX" run-workflow
```

`run-workflow` enqueues the payload, waits for the execution to finish, and prints the output payload. The item comes back with the property the task added:

```json
{
    "type": "FeatureCollection",
    "id": "tutorial/workflow-hello/item-1",
    "features": [
        {
            "id": "item-1",
            "collection": "tutorial",
            "properties": {
                "tutorial:processed": "2026-09-20T13:39:25.788603+00:00"
            }
        }
    ],
    "process": [
        {
            "workflow": "hello"
        }
    ]
}
```

Between those two commands, `process` took the payload off the queue, wrote a `CLAIMED` record to the state database, uploaded the payload to the payload bucket, and started the execution; the state machine invoked the function; and `update-state` recorded the result, stored the output payload, and published the item to the publish topic. See [Life of a payload](how-cirrus-works.md#life-of-a-payload).

## 4. Read what happened

The state database record:

```bash
cirrus manage "$RESOURCE_PREFIX" get-state tutorial/workflow-hello/item-1
```

```json
{
    "collections_workflow": "tutorial_hello",
    "itemids": "item-1",
    "state_updated": "SUCCEEDED_2026-09-20T13:39:25.890088+00:00",
    "updated": "2026-09-20T13:39:25.890088+00:00",
    "created": "2026-09-20T13:39:24.553341+00:00",
    "claimed_at": "2026-09-20T13:39:24.553341+00:00",
    "executions": [
        "arn:aws:states:us-east-1:000000000000:execution:cirrus-sandbox-hello:9d45818f-9d53-5cda-9eb7-43ffaf706bbe"
    ]
}
```

The state is the prefix of `state_updated`. `executions` holds the ARN of the one execution so far. Each field is described under [State database: Fields](../reference/state-database.md#fields).

The stored output payload, which is what `run-workflow` printed, and the execution's event history:

```bash
cirrus manage "$RESOURCE_PREFIX" get-output-payload tutorial/workflow-hello/item-1
cirrus manage "$RESOURCE_PREFIX" get-execution-events --payload-id tutorial/workflow-hello/item-1
```

Both resolve the payload ID to its most recent execution. The output payload is read from `executions/tutorial/workflow-hello/item-1/<execution-id>/output.json` in the payload bucket, and the events from Step Functions. On AWS, `get-execution-events --with-log-metadata` adds the Lambda request ID to the task event so `get-lambda-logs` can fetch that invocation's log lines; LocalStack's Step Functions emulation does not supply the request ID, so leave the flag off there.

## 5. Submit it again

```bash
<payload.json cirrus manage "$RESOURCE_PREFIX" process
```

Nothing runs. The record is `SUCCEEDED`, so `process` skips the payload and emits an `ALREADY_SUCCEEDED` [workflow event](../reference/workflow-events.md); `get-state` shows the same `executions` list as before. To run it again, set `replace` on the process definition and submit it with `process`:

```bash
python3 -c 'import json; p = json.load(open("payload.json")); p["process"][0]["replace"] = True; print(json.dumps(p))' \
    | cirrus manage "$RESOURCE_PREFIX" process
```

A few seconds later, `get-state` lists two executions and a newer `state_updated`. `process` rather than `run-workflow` here because `run-workflow` waits only while the record is `PROCESSING`, and a record that is already `SUCCEEDED` from the first run satisfies that at once, so it prints the earlier output before the rerun starts. The rules for which states rerun are in [The replace field and reruns](../reference/payload-schema.md#the-replace-field-and-reruns).

## 6. Clean up

```bash
aws cloudformation delete-stack --stack-name "$RESOURCE_PREFIX-hello-workflow"
```

The state database record and the stored payloads remain; they belong to the core stack.

## From here to a real task

The tutorial task has no dependencies, so its code fits inline in the template. A real task usually downloads assets, runs geospatial libraries, uploads results, and is built on [stac-task](https://github.com/stac-utils/stac-task), which handles the payload contract, asset download and upload, and output collection assignment. That means a container image and, for long or large jobs, AWS Batch instead of Lambda. [Writing a task](../building-pipelines/tasks.md) covers those, [Defining a workflow](../building-pipelines/workflows.md) covers retries and multi-task workflows, and [Feeders](../building-pipelines/feeders.md) covers replacing the hand-written payload with code that builds payloads from new data.
