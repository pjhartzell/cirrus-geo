# Cirrus

Cirrus is a [STAC](https://stacspec.org/)-based geospatial processing
framework built on serverless AWS infrastructure. Work moves through it as
payloads: JSON documents pairing inputs with instructions. The inputs are
STAC items or references to data elsewhere; the instructions name the
workflow to run and carry any settings its tasks need. Outputs collect in
the payload as well. As it moves through a workflow, each task returns it
updated, typically with new or modified STAC items.

Building a pipeline on Cirrus means writing three things: tasks, which do
the processing; workflows, which arrange tasks in sequence; and feeders,
which build payloads and push them onto a queue. The framework does the
rest. It reads each payload off the queue, starts the requested workflow,
and tracks the payload's state through to success or failure. When a
workflow succeeds, Cirrus publishes any output STAC items to an SNS topic.
From there a STAC catalog can ingest them, or another pipeline can process
them further.

The pipelines that populate
[Earth Search](https://www.element84.com/earth-search/), Element 84's
public STAC catalog of open Earth observation data, are built on Cirrus.

<div class="grid cards" markdown>

- :material-rocket-launch: **Quickstart**

    ---

    Deploy Cirrus to AWS or LocalStack and run a test workflow.

    [:octicons-arrow-right-24: Quickstart](getting-started/quickstart.md)

- :material-sitemap: **How Cirrus works**

    ---

    The components of a Cirrus deployment and the AWS architecture that
    runs them.

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
