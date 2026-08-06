# Workflows

Cirrus workflows are the component that puts the "pipe" in "pipeline".
Workflows model a transformation of an input item or set of input items with a
process definition into one or more output items via processing from one or
more tasks. Workflows are composed of one or more "tasks".

Cirrus workflows, being implemented via [AWS Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html), are written in
the [AWS States Language](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-amazon-states-language.html). Workflows are defined in `state-machine.json` files and require a companion `README.md`.

These `state-machine.json` files define the entire step function workflow. A non exhaustive list of configurable are :

- task definitions
- task input parameters
- task output parameters
- job definition
- job name
- task retry config
- error handling
- resource ARNs

The [state database](../../cirrus/70_statedb.md) tracks the state of items
processed at the workflow level.
