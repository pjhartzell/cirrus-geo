# Cirrus

Cirrus is a [STAC](https://stacspec.org/)-based geospatial processing
framework built on serverless AWS infrastructure. It supplies the parts
that are the same in every processing pipeline — queueing, workflow
execution, state tracking, publishing — so you can focus on your
processing code. And because inputs and outputs are STAC items, results
are immediately ready for ingest into a STAC catalog or use in another
Cirrus workflow.

Cirrus is proven in production. The pipelines that populate
[Earth Search](https://www.element84.com/earth-search/), Element 84's
public STAC catalog of open Earth observation data, run on Cirrus for
both daily ingest and full-catalog reprocessing.

<div class="grid cards" markdown>

- :material-rocket-launch: **Quickstart**

    ---

    Run Cirrus on LocalStack and submit a test workflow.

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
