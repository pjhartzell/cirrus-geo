# Workflows

A workflow models the transformation of an input payload into one or more
output items via processing through one or more tasks. Workflows are
implemented as [AWS Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html)
state machines, written in the [AWS States Language](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-amazon-states-language.html).

A workflow definition is a CloudFormation template that deploys a
`AWS::StepFunctions::StateMachine` resource, along with the IAM role the
state machine assumes to invoke its tasks. See
[Writing workflow definitions](definitions.md) for the required structure and
naming, and the in-repo `minimal` workflow
(`cloudformation/workflows/minimal/state_machine.yaml`) for a working
example.

The `process` Lambda function dispatches each incoming payload to the Step
Functions execution named in the payload's `process` definition. When an
execution reaches a terminal status, the `update-state` Lambda function
records the result in the [state database](../../cirrus/70_statedb.md) and
handles [chaining](chaining.md) to any subsequent workflow.
