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

![Cirrus architecture overview](cirrus/images/arch-overview.png)

<div class="grid cards" markdown>

- :material-rocket-launch: **Getting started**

    ---

    Core concepts and how a payload moves through Cirrus.

    [:octicons-arrow-right-24: Getting started with Cirrus](cirrus/10_intro.md)

- :material-sitemap: **Architecture**

    ---

    The AWS pieces of a Cirrus deployment and how they fit together.

    [:octicons-arrow-right-24: Cirrus architecture](cirrus/20_arch.md)

- :material-code-json: **Payloads**

    ---

    The Cirrus Payload format: items, process definitions, and output options.

    [:octicons-arrow-right-24: Cirrus Payload](cirrus/30_payload.md)

- :material-console: **CLI**

    ---

    Manage and interact with Cirrus deployments from the command line.

    [:octicons-arrow-right-24: The Cirrus CLI](cli/00_intro.md)

</div>
