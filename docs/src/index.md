# Cirrus

Cirrus is a [STAC](https://stacspec.org/)-based geospatial processing pipeline
platform, implemented using a scalable architecture deployed on AWS. Cirrus
provides the generic infrastructure for processing, allowing a user to focus on
implementing the specific processing logic for their data.

As input, Cirrus takes a payload — a STAC ItemCollection with an attached
`process` definition block — and runs it through a workflow that generates one
or more output STAC Items. Outputs are stored in S3 and broadcast via an SNS
topic, and subscriptions to that topic can trigger additional workflows or
external processes, such as indexing into a STAC API.

![Cirrus architecture overview](images/arch-overview.png)

<div class="grid cards" markdown>

- :material-rocket-launch: **Quickstart**

    ---

    Deploy Cirrus to AWS or LocalStack and run a test workflow.

    [:octicons-arrow-right-24: Quickstart](getting-started/quickstart.md)

- :material-sitemap: **How Cirrus works**

    ---

    The AWS pieces of a Cirrus deployment and how they fit together.

    [:octicons-arrow-right-24: How Cirrus works](getting-started/how-cirrus-works.md)

- :material-code-json: **Payloads**

    ---

    The Cirrus Payload format: items, process definitions, and output options.

    [:octicons-arrow-right-24: Cirrus Payload](reference/payload-schema.md)

- :material-console: **CLI**

    ---

    Manage and interact with Cirrus deployments from the command line.

    [:octicons-arrow-right-24: The Cirrus CLI](cli/using-the-cli.md)

</div>
