# Using the CLI

## Introduction

Cirrus itself is [STAC](https://stacspec.org/)-based geospatial processing pipeline platform deployed
on AWS and is a constellation of associated pieces of AWS infrastructure. The
pieces of a Cirrus deployment like the lambdas, SQS, S3 buckets and other can be
managed and interacted with using common AWS management tools like the AWS GUI
or AWS CLI.

However the nature of a Cirrus deployment can make direct
management via AWS tools difficult to do things like batch reruns, manage
deployments, individual lambda invocations, and more. There can be multiple
cirrus deployments and Cirrus infrastructure may co-exist in an AWS account with non Cirrus resources further complicating this management. The Cirrus CLI was built to simplify dealing with these issues.

## What Is the Cirrus CLI?

To ease the management of a cirrus deployment the cirrus-geo library has a
built in command line tool designed to streamline the developer
experience when using and interacting with a Cirrus deployment.

The Cirrus CLI is a python tool built using the [click](https://click.palletsprojects.com/en/stable/) library with commands
specific to Cirrus. Example use cases would be to list all available cirrus
deployments, list lambdas in a given deployment, and even directly trigger a
workflow with an input Payload by sending the payload directly to the SQS queue
monitored by the `process` lambda, and more.

## What if I'm using an older version of Cirrus?

You can use the [older CLI tool](https://pypi.org/project/cirrus-mgmt/) which is a standalone module and can be
installed via pip.

## How To Use the Cirrus CLI?

A few simple steps are all it takes to set up the Cirrus CLI for use.

1. Install
2. Authenticate
3. Run commands

## Cirrus CLI Quick Start

If you understand the broader background and structure of Cirrus, cirrus
deployments and the cirrus CLI tool and you want to jump right into using the
CLI tool here is what an example workflow might look like. These are one way of accomplishing these steps, personal and organizational requirements may differ.

1. Install requirements

    ``` bash
    pipx install 'cirrus-geo[cli]'
    ```

2. Authenticate (if necessary)

    ``` bash
    aws sso login --profile your-config-profile-here
    ```

3. Use the Cirrus CLI

    ``` bash
    cirrus mgmt deployment-name-here list-lambdas
    ```

And that's it! If you would like more in depth explanations on how to use the
tool, please proceed.

## Installing

Built using python [click](https://click.palletsprojects.com/en/stable/) library and included in the broader [cirrus-geo](https://github.com/cirrus-geo/cirrus-geo)
library, you can install the CLI tool on its own or alongside other project
requirements. A standalone CLI installation might look like

``` bash
pipx install 'cirrus-geo[cli]'
```

Another way is to use a more modern tool like `uv` to run specific CLI
commands in an ephemeral environment.

``` bash
uvx --from 'cirrus-geo[cli]' cirrus [COMMAND]
```

## Authentication

Because the Cirrus CLI interacts directly with AWS resources via the AWS python API
with the boto3 library, you will have to be authenticated with AWS. We
recommend following your organization's best practice recommendations for
authentication. One way you could do so is to use the [AWS CLI tool](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html).

Look [here](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html) for an in depth explanation of authentication options with the AWS
command line tool and how to configure SSO login.

The Cirrus CLI will only need to be installed once, but authenticating with AWS
will be necessary for each new session as AWS credentials expire and must be
refreshed every so often. This can be easily accomplished with the AWS CLI
single sign on (SSO) option.

After you have built your config file according to organizational or personal
preference you can login with

``` bash
aws sso login --profile your-named-profile
```

Once you have successfully SSO'd setup will be complete for the Cirrus CLI

## The Cirrus CLI and Cirrus Deployments

The Cirrus CLI is designed around interacting with a different cirrus deployments. Many
of the commands are focused on interacting with a specific cirrus 'deployment',
like invoking a specific workflow to run in a specific deployment. A 'cirrus
deployment' can be considered to be the collection of related AWS resources for
a single cirrus deployment. For the Cirrus CLI, a 'deployment' is represented as a
collection of essential environment variables that are necessary to interact
with the correct AWS resources for a deployment, like relevant ARNs or SQS queue
URLs. These environment variables for connecting to the correct resources are
stored in the [AWS Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html)

### Deployments and Parameter Store

As previously mentioned, using the Cirrus CLI requires knowing deployment specific
environment variables to make AWS API calls to the correct resources. These
environment variables are stored in the AWS Parameter Store. For example, the
`process` lambda requires the "CIRRUS_PAYLOAD_BUCKET" environment variable to
know what bucket to dump payloads into for storage. When running commands on a
specific deployment the Cirrus CLI will automatically retrieve these environment
variables based on the deployment name you pass.

### Parameter Store

The parameter store has a hierarchical storage system centered around the use of
`/` in parameter names. More information on parameter hierarchies can be found
on the [AWS parameter store documentation](https://docs.aws.amazon.com/systems-manager/latest/userguide/sysman-paramstore-hierarchies.html). This hierarchial organization is
used to ensure deployments can be found under common prefixes, and enables for
easy use if you wish to directly search the parameter store yourself.

The Cirrus CLI utilizes the parameter store to store these critical environment
variables for different deployments. When you run a command on a specific
named cirrus deployment the Cirrus CLI first retrieves the environmental variables for
that cirrus deployment from the parameter store and then uses them to execute
commands like `list-lambdas`

A pointer system is used to identify the parameter store prefix for a given
deployment to ensure that we can search and retrieve only the environment
variables for a given deployment without having to parse a large amount of
returned parameters. Using this pointer the Cirrus CLI can then retrieve the related
environment variables.
