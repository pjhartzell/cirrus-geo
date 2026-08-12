# Cirrus

Cirrus is a [STAC](https://stacspec.org/)-based geospatial processing pipeline
platform, implemented using a scalable architecture deployed on AWS. Cirrus
provides the generic infrastructure for processing, allowing a user to focus on
implementing the specific processing logic for their data.

<div class="grid cards" markdown>

- :material-rocket-launch: **Quickstart**

    ---

    Deploy Cirrus to AWS or LocalStack and run a test workflow.

    [:octicons-arrow-right-24: Quickstart](getting-started/quickstart.md)

- :material-sitemap: **How Cirrus works**

    ---

    The AWS pieces of a Cirrus deployment and how they fit together.

    [:octicons-arrow-right-24: How Cirrus works](getting-started/how-cirrus-works.md)

- :material-code-json: **Building pipelines**

    ---

    Author the tasks, workflows, and feeders that make up a pipeline.

    [:octicons-arrow-right-24: Building pipelines](building-pipelines/tasks.md)

- :material-console: **CLI**

    ---

    Manage and interact with Cirrus deployments from the command line.

    [:octicons-arrow-right-24: The Cirrus CLI](cli/using-the-cli.md)

</div>

Cirrus is the processing pipeline behind
[Earth Search](https://www.element84.com/earth-search/), Element 84's public
STAC catalog of open Earth observation data. Earth Search has processed
collections of millions of items through Cirrus, at sustained rates where
AWS account quotas, not the framework, became the practical ceiling. See
[Scaling and throughput](operating/deployment.md#scaling-and-throughput)
for the knobs that govern throughput.
