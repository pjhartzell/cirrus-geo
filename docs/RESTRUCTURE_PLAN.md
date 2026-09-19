# Docs restructure plan (2026-09)

Second pass over the 2026-08 restructure. Scope: regroup the navigation, give every repeated fact one home, split two overgrown pages, add three pages, and rewrite How Cirrus works. No page is rewritten wholesale except How Cirrus works and the three new pages.

Ground rules from `CLAUDE.md` apply to every phase. Three additions for this plan:

- **Every page is audited, not only the pages that move.** Each claim on each page is checked against `src/`, `cloudformation/`, or `CHANGELOG.md`. Prose survives only where it checks out. Wrong claims are corrected; unverifiable claims are cut and named in the commit body, or left with a note in `docs/CODE_BEHAVIOR_NOTES.md` when the code itself looks wrong.
- **Review happens once, at the end.** Commits are made per phase so the history is legible, but the reviewer reads the finished site, not the individual commits.
- **Audit findings are recorded in the commit body** as the source files each page was checked against, so a reviewer can retrace a claim.

Each phase ends with `uv sync --group docs --extra cli && uv run mkdocs build --strict` passing.

## Target navigation

```
Home
Getting started
  How Cirrus works                 getting-started/how-cirrus-works.md
  Quickstart                       getting-started/quickstart.md
  Follow a payload through Cirrus  getting-started/follow-a-payload.md
Building pipelines
  Tasks
    Writing a task                 building-pipelines/tasks.md
    Batch infrastructure           building-pipelines/batch-infrastructure.md
  Workflows
    Defining a workflow            building-pipelines/workflows.md
    Batch tasks in a workflow      building-pipelines/batch-workflow-structure.md
    Chaining workflows             building-pipelines/chaining-workflows.md
  Feeders                          building-pipelines/feeders.md
Operating
  Deployment                       operating/deployment.md
  Scaling and quotas               operating/scaling.md            (new, phase 2)
  Monitoring                       operating/monitoring.md
  Upgrading to 2.0                 operating/upgrading.md
CLI
  Using the CLI                    cli/using-the-cli.md
  Common workflows                 cli/common-workflows.md
  Command reference                cli/reference.md
Python library
  Overview                         api/index.md                    (new, phase 6)
  CirrusPayload, StateDB, PayloadBucket, Events, Errors and exceptions, Deployment class
Reference
  Payload schema                   reference/payload-schema.md
  Lambda functions                 reference/lambda-functions.md
  Workflow events                  reference/workflow-events.md    (new, phase 1)
  State database                   reference/state-database.md
  Payload bucket                   reference/payload-bucket.md
  HTTP API                         reference/http-api.md
About
  Contributing, Changelog, License
```

## Canonical homes

Each fact below is explained in more than one place today. After this plan it is explained in one place and linked from the others.

| Fact | Canonical home | Pages that currently restate it |
| --- | --- | --- |
| Process Lambda intake: record normalization, extraction, S3 fetch, validation, claim | Lambda functions, `process` | feeders.md, how-cirrus-works.md |
| Stack inventory (six nested stacks plus bootstrap) | Deployment, Stack layout | quickstart.md Overview |
| Lambda request-ID log filtering | Monitoring, CloudWatch logs | tasks.md "Logs" |
| Batch placement overhead, Earth Search examples | Writing a task, Lambda vs Batch | batch-workflow-structure.md |
| Oversized payload mechanism and the 120,000-byte limit | Payload bucket, Oversized payloads | workflows.md Keep payloads small, feeders.md |
| Step Functions status to state mapping, `InvalidInput`, `TimedOutError` | Lambda functions, `update-state` | workflows.md Capturing errors, monitoring.md Workflow events |
| `get-state`, `query`, `get-input-payloads` usage | CLI common workflows | state-database.md, monitoring.md |
| Bulk rerun shell loop | CLI common workflows | monitoring.md Rerunning payloads |
| Event types, event destinations, metrics stack wiring, Timestream deprecation | Workflow events (new) | monitoring.md, deployment.md, http-api.md, how-cirrus-works.md |
| `pre-batch` / `post-batch` contract | Lambda functions | batch-workflow-structure.md, batch-infrastructure.md, tasks.md, how-cirrus-works.md |
| `replace` and rerun state table | Payload schema | lambda-functions.md `process` step 1 |
| Workflow naming and `process` dispatch | Defining a workflow, Naming and dispatch | deployment.md Workflow stacks, how-cirrus-works.md |
| Lambda concurrency, queue priority, quotas and limits | Scaling and quotas (new) | deployment.md |
| `cirrus` package: CLI and `cirrus.lib` | Python library overview (new) | how-cirrus-works.md |
| `run-workflow` validates client-side, `process` does not | CLI common workflows, Run a workflow | follow-a-payload.md (keeps the narrative, links the fact) |

## Phases

### Phase 0: navigation and titles

Mechanical. No prose changes beyond H1s.

- `mkdocs.yml`: regroup per the target navigation, for existing pages only. New pages are added to the nav in the phase that creates them. `navigation.sections` in the theme features already renders top-level entries as sidebar sections; verify the three added sections render before committing.
- H1 and nav title agree on every page. Sentence case throughout. Changes: `# Cirrus Payload` stays as H1, nav entry becomes "Payload schema" → H1 becomes `# Payload schema`; `# Cirrus API Endpoints` → `# HTTP API`; `# Workflow chaining` → `# Chaining workflows`; `# CLI reference` → `# Command reference`; `# State Database` → `# State database`; `# Payload Bucket` → `# Payload bucket`; `# Follow a Payload Through Cirrus` → `# Follow a payload through Cirrus`; `# Tasks` → `# Writing a task`; `# Workflows` → `# Defining a workflow`; `# Wiring a Batch task into a workflow` → `# Batch tasks in a workflow`. Nav "Monitoring & troubleshooting" → "Monitoring".
- Before each H1 rename, grep `docs/src` for inbound `#`-anchors to that heading. H1 anchors are rarely linked, but check.
- Home page card for "How Cirrus works" is unchanged. Home page card for CLI already points at `cli/using-the-cli.md`.

Commit: `docs(nav): regroup building-pipelines, promote CLI and library, align titles`

### Phase 1: Workflow events reference page

Creates `reference/workflow-events.md` and makes it the one home for events.

- New page content, in this order: what an event is and who emits it (`WorkflowEventManager` in `cirrus.lib.events`, called from `process` and `update-state`); the event type table, moved from monitoring.md; the two paragraphs distinguishing `RECORD_EXTRACT_FAILED` from `NOT_A_PROCESS_PAYLOAD` and `FAILED`/`TIMED_OUT`/`INVALID`, moved from monitoring.md; event fields; destinations (SNS topic, CloudWatch log group and the two metric filters, namespace), consolidated from monitoring.md "Where events go" and deployment.md "Workflow event metrics"; the Timestream deprecation note, once.
- Verify the event table against `WFEventType` in `src/cirrus/lib/enums.py` and the emit sites in `src/cirrus/lib/events.py`. Verify destinations against `cloudformation/core/metrics.yaml` and `core/functions.yaml`.
- monitoring.md: "Workflow events" section shrinks to what the operator does with events (subscribe to the topic, read `/stats`, look at the metrics namespace) and links to the reference.
- deployment.md: "Workflow event metrics" shrinks to the `EnableWorkflowMetrics` parameter and what the metrics stack creates, with a link. The Timestream paragraph is cut. The `CIRRUS_EVENT_DB_AND_TABLE` row in the environment variable table links to the reference instead of to the cut section.
- http-api.md `/stats`: keep the data-source order (it is API behavior), replace the Timestream explanation with a link.
- Fix inbound links to `monitoring.md#workflow-events` (http-api.md has two, payload-schema.md has one).

Commit: `docs(reference): add workflow events page, make it the single home for event types and destinations`

### Phase 2: split Scaling and quotas out of Deployment

- New `operating/scaling.md` receives, moved unchanged: "AWS service quotas and limits" (with its Quotas and Limits subsections), "Scaling and throughput" (Process Lambda concurrency, Process queue priority, Batch-backed workflows). Add a two-sentence intro naming the three throughput controls.
- deployment.md keeps: intro, Stack layout, Main stack parameters, Workflow stacks, VPC considerations, Workflow event metrics (post phase 1), Environment variables, Required deploy permissions, Deleting a deployment, Other deployment approaches.
- deployment.md "Workflow stacks": cut the ARN-prefix mechanism restatement to one sentence plus a link to Defining a workflow, Naming and dispatch.
- Fix inbound links to `deployment.md#scaling-and-throughput` and `#compute-environment` cross-references.

Commit: `docs(operating): split scaling and quotas out of deployment`

### Phase 3: Lambda functions as canonical

- lambda-functions.md: replace the opening "The `function` component type refers to" sentence. Fix the `process` Trigger bullet that says feeders can publish "via the process SNS topic": `cloudformation/core/base.yaml` creates only `PublishTopic` and `WorkflowEventTopic`, so the bullet becomes "directly, or through an SNS topic subscribed to the queue" with a link to Feeders. In `process` step 1, replace the prose restatement of which states run and skip with a link to Payload schema, The replace field and reruns.
- feeders.md: "What the process Lambda accepts" shrinks to the message shapes `extract_record` accepts (SQS body, SNS envelope, `{"url": ...}` reference) and what happens to a rejected message, with a link to Lambda functions for the full sequence. Verify the shapes against `src/cirrus/lib/utils.py`. "Payload validation" stays as a link.
- batch-infrastructure.md "Job parameters": keep the `Ref::url` expansion and the requirement to read `url` and write `url_out`; cut the restated description of what `pre-batch` and `post-batch` do, link instead.
- tasks.md "Batch tasks": the `pre-batch`/`post-batch` sentence becomes one clause plus a link.

Commit: `docs(reference): make lambda-functions the single home for process intake and the batch shuttle contract`

### Phase 4: Tasks and Workflows cleanup

- tasks.md: move the "Logs" block (request-ID filtering, `aws logs filter-log-events` example, `get-execution-events --with-log-metadata`) to monitoring.md "CloudWatch logs per function". Keep the `<a id="lambda-logs">` anchor's inbound links working by updating workflows.md and monitoring.md references. tasks.md "Structured logging" keeps `CirrusLoggerAdapter` and the logger name prefixes; verify the prefix list against `src/cirrus/lib/logging.py`.
- tasks.md "Lambda vs Batch": receives "When Batch overhead dominates" from batch-workflow-structure.md, moved unchanged, as a subsection. The Earth Search examples are user-attested; keep as written.
- workflows.md "Keep payloads small": reduce to one design-guidance bullet under Design guidance, linking Payload bucket, Oversized payloads. Cut the `MAX_PAYLOAD_LENGTH` explanation.
- workflows.md "Capturing errors": keep the `ErrorPath`/`CausePath` requirement and the placeholder-message consequence; cut the `FAILED`/`INVALID`/`TIMED_OUT` paragraph and link to Lambda functions, `update-state`.
- Design guidance stays on workflows.md. Splitting it is deferred; revisit after the page is trimmed.

Commit: `docs(building-pipelines): move log filtering to monitoring, batch overhead to tasks, cut workflow restatements`

### Phase 5: CLI cookbook as canonical for commands

- state-database.md: cut "Querying via the Cirrus CLI"; add one sentence under the intro's usage list linking CLI common workflows.
- monitoring.md "Querying the state database": keep what to look for (state filter, `--error-prefix`, time window) in prose; replace the three command examples with a link to the cookbook. "Rerunning payloads": cut the shell loop, keep the two sentences on what `--rerun` does and the link to Payload schema. "Step Functions console": keep the console-URL and `executions` field explanation; cut the command examples, link the cookbook.
- common-workflows.md "Run a workflow and wait for the result": add the sentence that `run-workflow` validates the payload before submitting and `process` does not. Verify against `src/cirrus/management/commands/manage.py`.
- follow-a-payload.md: the validation admonition becomes two sentences plus a link to that cookbook section.
- quickstart.md Overview: cut the six-stack bullet list, keep the mermaid diagram and a link to Deployment, Stack layout. Next steps: drop the How Cirrus works bullet.

Commit: `docs(cli): make common-workflows the single home for state-db and rerun commands`

### Phase 6: Python library overview

- New `api/index.md`: what `cirrus.lib` is (the library the five Lambda functions are built on), what user code imports it for (`CirrusPayload` for feeders, `cirrus.lib.logging` for tasks, `StateDB` and `PayloadBucket` for tooling), what `cirrus.management` is (the layer under the CLI, needs the `cli` extra), and a table linking the six module pages. Seeded from how-cirrus-works.md "The `cirrus` package". Verify imports against `src/cirrus/lib/__init__.py` and `pyproject.toml` extras.
- Add to nav under Python library.

Commit: `docs(api): add library overview page`

### Phase 7: rewrite How Cirrus works

Last, because it links to everything and its scope depends on where the earlier phases put things. Outline:

```
# How Cirrus works
Intro: payload in, workflow of tasks runs, STAC items out, published. Three to four sentences.

## The payload
What a Cirrus Payload is, the process block, STAC in and STAC out as intent.
One sentence on validation scope, linking Payload schema.

## What you build and what Cirrus provides
Table: pipeline side (feeders, workflows, tasks) and framework side
(process, update-state, pre-batch, post-batch, api, queue, state database,
payload bucket, topics). Architecture diagram here.

## Life of a payload
Numbered lifecycle: feeder → queue → process → execution → update-state →
publish and chain. Events as a one-line note on the update-state step.
Link to Follow a payload as the hands-on version.

## Workflows are Step Functions state machines
Naming convention, Lambda or Batch tasks, Fail state. One sentence on
pre-batch/post-batch linking Batch tasks in a workflow.

## Where to go next
Three links: Deployment, CLI, Python library.
```

- Check `docs/src/images/arch.png` (untracked, added this branch) for the deprecated Timestream box before placing it. If it still shows one, either redraw or keep a one-line caption linking the Workflow events deprecation note.
- Update inbound anchors: state-database.md and lambda-functions.md link `how-cirrus-works.md#architecture`.
- Every sentence names a concrete thing or is cut.

Commit: `docs(getting-started): rewrite How Cirrus works around the pipeline/framework split`

## Deferred

- Splitting Design guidance out of Defining a workflow.
- Moving "Updating Batch resources safely" from Batch infrastructure to Operating. It is an update-time concern but is specific to pipeline-owned resources; left where it is.
- Adding a troubleshooting section to Monitoring. The nav title is changed to match the page instead.
