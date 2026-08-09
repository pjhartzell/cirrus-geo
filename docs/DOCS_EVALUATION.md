# Cirrus docs evaluation and restructuring proposal

Status: proposal for review. Produced 2026-08-07 on branch `docs-overhaul`, after the
DOCS_PLAN.md overhaul completed (sessions 1–3).
Inputs: a page-by-page audit of all 39 pages under `docs/src/`, and an independent
code-derived map of the public surface (`src/cirrus/`, `cloudformation/`, CLI command
tree). Code was treated as ground truth for coverage and structure; claim-by-claim
fact-checking is deferred to the rewrite.

## Verdict

The overhaul fixed correctness and tooling but kept the inherited page inventory, and
that inventory is the remaining problem. The site has no single home for its central
facts — the rerun/`replace` rule is told five times, the CLI command tour four times,
the component taxonomy three times — and the top-level nav mixes genres in both
directions (schema references under Guides, tutorials under Reference). The
three-persona routing in the intro is broken as shipped (two of three personas have no
links) and no other page references it. The recommendation is a smaller site (~30 pages
from 39) reorganized around what the reader is doing, with exactly one home per fact.

## Findings

### Audience

The intro's three personas (infrastructure engineers, framework users, algorithm
developers) do not survive contact with the site:

- The routing section itself is broken: "Infrastructure Engineers" and "Framework
  Users" get a one-line description and no reading list; "Algorithm Developers" gets
  four bullets, one of which (`cirrus-lib` documentation) is plain text, not a link.
- No other page tags content by persona or refers back to the scheme. The upgrading
  guide uses a different, incompatible partition (operators / CLI users / library
  consumers), so two audience taxonomies are live at once and neither governs the nav.
- Every persona's real reading list cuts across both Guides and Reference, so the
  personas and the nav actively work against each other.

The code confirms the suspicion that "framework user" and "algorithm developer" are
the same person: the entire user-authored surface is three things — workflows (ASL
state machines matched by naming convention), tasks (stac-task code, out of repo), and
feeders (pure convention, zero framework code) — and one person building a pipeline
touches all three plus the payload contract. The real split is **people who build
pipelines** and **people who deploy and operate the platform**, with heavy overlap.
Two further audiences are served adequately by dedicated sections and need no routing:
library consumers (generated Library API) and contributors (About).

**Recommendation: delete the persona-routing section entirely and let the nav do the
routing.** Sections named for activities (get started / build pipelines / deploy &
operate / look things up) are self-navigating; no page should ever say "if you are an
X, go to Y."

### Duplication clusters

| Topic | Told in | Proposed single home |
| --- | --- | --- |
| Rerun/`replace` state-eligibility rule | 30_payload, 50_operation, 80_monitoring, functions/process, 70_statedb (partial) | Payload schema reference (`replace` field); StateDB page keeps the CLAIMED *mechanism* |
| CLI command tour (`get-execution*`, `query`, rerun piping, templating) | 17_end_to_end, cli/04_commands, 80_monitoring, 50_operation | CLI cookbook; walkthrough keeps narrative only, monitoring links |
| Component taxonomy (feeders/tasks/workflows/functions) | 10_intro, components/index, 20_arch glossary | Concepts page (merged intro+arch) |
| `pre-batch`/`post-batch` `url`/`url_out` contract | functions/pre_batch, functions/post_batch, tasks/batch, workflows/batch | Lambda functions reference page; batch guides link |
| Step Functions retry/backoff/jitter JSON | workflows/definitions (explained), workflows/batch, tasks/batch (unexplained copies) | Workflows guide |
| `run-workflow` exit codes 0/10/11 | 15_quickstart, 17_end_to_end, cli/04_commands | CLI cookbook |
| Nested-stack layout (six stacks) | 15_quickstart (diagram), 40_config-deploy (table) | Deployment page; quickstart keeps the diagram and links |
| `${ResourcePrefix}-<name>` workflow naming | workflows/definitions, 40_config-deploy, echoed in 70_statedb / 78_api_endpoints | Workflows guide |
| `ErrorPath`/`CausePath` requirement | workflows/definitions, tasks/batch | Workflows guide |
| StateDB query filter parameters | 50_operation, 80_monitoring, 70_statedb, cli/04_commands, 78_api_endpoints | Generated CLI reference for flags; 78 for the HTTP form |
| `api` Lambda endpoint surface | functions/api (summary), 78_api_endpoints (full) | 78; the functions page keeps one paragraph + link |

### Navigation and genre problems

- Reference-shaped pages under Guides: `30_payload` (field tables, schema),
  `40_config-deploy` (parameter/stack reference that explicitly defers all how-to
  content to the quickstart).
- Guide-shaped pages under Reference: `components/feeders/index` (worked Python
  feeder), `components/tasks/index` (three-Dockerfile tutorial progression).
- Title collisions: two unrelated pages both titled "Deployment"
  (`cirrus/40_config-deploy` and `api/deployment`); near-twins "Batch tasks" /
  "Batch in workflows" for two pages that are easy to conflate.
- Title/content mismatches: "Operations" delivers only bulk reruns while "Monitoring"
  covers what "Operations" implies; "Tips and tricks" (plural) contains one tip.
- Ordering: Getting Started runs Quickstart → End-to-end walkthrough → Concepts, so
  both hands-on pages precede the page that defines the vocabulary they use. The CLI
  section uses `cirrus list-deployments` and the `mgmt` alias pages before either is
  introduced.
- Stub pages: `components/workflows/index` (4 sentences), `components/index`
  (duplicate taxonomy), `components/functions/index` (fine but only needed because the
  five function pages are separate).

### Defects to fix regardless of restructure

- `cirrus/50_operation.md` still shows the bulk-rerun `xargs` pipe into a single
  `process` invocation — the exact pattern DOCS_PLAN task 4.1 identified as broken and
  replaced with a line-by-line loop in `cli/04_commands.md`. This page was missed.
- `cirrus/20_arch.md` glossary: "workflow: An AWS Step Function consisting of 1 or
  more tasks" — the `minimal` workflow used throughout Getting Started has zero tasks.
- Install commands disagree: `pip install 'cirrus-geo[cli]>=1.0.0'` (cli/00_intro) vs
  unpinned `pipx install 'cirrus-geo[cli]'` (cli/01_install) on adjacent pages.
- Typos: "One you have successfully SSO'd" (cli/02_auth), "Interestly"
  (components/workflows/batch).
- `api/errors.md` is the only Library API page with no hand-written intro — and it's
  the page most likely to be landed on from a traceback. It should orient the reader
  on `cirrus.lib.errors` vs `cirrus.exceptions`.
- `cli/00_intro.md`'s quick-start example uses `list-lambdas`. The command is real
  (`management/commands/manage.py`) — the audit flagged it as possibly stale because
  no other page mentions it. No fix needed beyond the page's planned rewrite; noted so
  it isn't "corrected" away.

### Coverage gaps (code says it, docs don't)

- **Logging contract for user code.** `CirrusLoggerAdapter` and the reserved parent
  logger names (`task`, `feeder`, `function`, `lambda_function`, `cirrus.lib`) are a
  concrete contract for task/feeder authors — name your logger under one of these
  prefixes to get Cirrus's structured JSON logging — documented nowhere.
- **Throughput ceiling.** The `process` Lambda's reserved concurrency of 16 caps
  concurrent workflow starts. The deployment page's quotas section mentions Lambda
  concurrency generically; the specific, load-bearing cap is not stated.
- **Consolidated env var reference.** The `CIRRUS_*` env vars are scattered across
  function pages and the CLI deployments page; no single table exists. Natural home:
  the deployment page.
- **CLI user IAM permissions.** `cli/02_auth.md` covers AWS SSO generically and never
  says what permissions a CLI user's identity needs (vs the deploy role, which the
  deployment page covers).
- **`cirrus manage show`, `invoke-lambda`, `list-lambdas`** appear only in the
  generated reference, never in any curated content. Acceptable, but the cookbook's
  debugging section could earn `invoke-lambda`.
- `cirrus.lib.errors.InvalidInput` does not exist as a class; only
  `stactask.exceptions.InvalidInput` is usable by task authors to signal INVALID (the
  string match on the fully-qualified legacy name is intentional backcompat, per
  OPEN_QUESTIONS resolution). The update-state page documents the legacy name; the
  tasks guide should state plainly which exception a task author raises today.

## Proposed information architecture

Principles: sections named for activities, not roles; each fact has one home; guides
do tasks, reference enumerates contracts; no page under ~15 lines unless it's a
genuinely simple fact.

```
Home
Getting started
├─ How Cirrus works          concepts: merged intro + architecture
├─ Quickstart                deploy and run the minimal workflow
└─ Follow a payload through  slimmed walkthrough (narrative only)
Building pipelines
├─ Workflows                 authoring state machines (canonical: naming, errors, retry)
├─ Chaining workflows
├─ Tasks                     authoring tasks (stac-task, Docker, Lambda vs Batch)
├─ Batch
│  ├─ Batch workflow structure    (was workflows/batch)
│  └─ Batch infrastructure        (was tasks/batch, incl. safe-update playbook)
└─ Feeders
Deploying & operating
├─ Deployment                stacks, parameters, env vars, quotas, scaling/tuning
├─ Monitoring & troubleshooting   absorbs bulk reruns
└─ Upgrading to 2.0
Reference
├─ Payload schema            (was 30_payload; canonical replace rule)
├─ State database
├─ Payload bucket
├─ HTTP API                  (was 78_api_endpoints)
├─ Lambda functions          one page, five sections
├─ CLI
│  ├─ Using the CLI          install + auth + deployment discovery
│  ├─ Command reference      generated (mkdocs-click)
│  └─ Common CLI workflows   cookbook (canonical command tour)
└─ Library API               six generated pages (unchanged)
About                        contributing / changelog / license (unchanged)
```

~30 pages (counting the six generated Library API pages) versus 39 today. The numbered
filename scheme (`10_`, `15_`, …) should be dropped during the moves — the nav orders
pages, and the numbers are already lying (17 between 15 and 20, 78 wedged before 80).

### Page briefs

**Home** (`index.md`). Keep the one-paragraph pitch and architecture image; re-point
the four cards at the new nav (Quickstart, How Cirrus works, Building pipelines,
CLI). Cut the sentence that duplicates the concepts page's opening.

**How Cirrus works** (merge `cirrus/10_intro.md` + `cirrus/20_arch.md`). One page:
what Cirrus is, the architecture diagrams with the payload-lifecycle walkthrough, the
canonical component taxonomy (feeders / tasks / workflows / functions — the only
statement of it in the site), the framework-vs-user-code boundary (from the code map:
Cirrus runs and tracks workflows; users author workflows, tasks, and feeders), and the
glossary with "see also" links into reference pages. Delete: the persona-routing
section, the unannotated 12-item AWS services list (fold the meaningful entries into
the architecture prose), the Earth Search collection trivia (park one paragraph max as
a "who uses this" note or drop). Fix the "1 or more tasks" glossary error.

**Quickstart** (`cirrus/15_quickstart.md`, trimmed). Keep structure and commands (they
verified well). Collapse the fully-duplicated LocalStack narrative into the AWS path
with tabbed blocks or per-step call-outs; state expected wall-clock time and rough
cost. Exit codes move to the cookbook; link instead.

**Follow a payload through Cirrus** (slimmed `cirrus/17_end_to_end.md`). Keep the
narrative arc — submit, watch state, inspect execution, fetch output — and the
genuinely unique material (client-side vs server-side validation, `get-state` backoff,
the worked state-record JSON). Drop the per-command flag semantics; every command
mention links to the cookbook or generated reference. This page and the cookbook are
currently the closest duplicate pair; after slimming, the walkthrough is the tutorial
and the cookbook is the task-oriented how-to. If the slimmed page ends up under ~80
lines, fold it into the quickstart as a final section instead.

**Workflows** (merge `components/workflows/index.md` into
`components/workflows/definitions.md`). Canonical home for: state-machine structure,
`${ResourcePrefix}-<name>` naming (and why: `CIRRUS_BASE_WORKFLOW_ARN`, EventBridge
prefix match), `ErrorPath`/`CausePath` error capture, the retry/backoff/jitter
pattern, and the payload-size constraint (EventBridge ~248 KiB; keep payloads small,
oversized payloads go by S3 reference). Keep the six best-practices items but under a
clearly labeled "Design guidance" heading so the genre shift is signposted.

**Chaining workflows** (`components/workflows/chaining.md`, near-unchanged). Add the
back-link to the payload schema's `chain_filter` entry.

**Tasks** (was `components/tasks/index.md`). Now honestly a guide. Keep the Docker
progression and Lambda-vs-Batch decision lists (fold the one-bullet "either" list into
prose). Add: the logging contract (logger naming / `CirrusLoggerAdapter`), and the
plain statement that `stactask.exceptions.InvalidInput` is the exception a task raises
to be classified INVALID. The Lambda log-filtering walkthrough stays (only home).

**Batch workflow structure** (was `components/workflows/batch.md`). The
`parallel`-wrapper pattern, Batch error handling, the worked ASL example — with the
retry JSON reduced to one instance linking to Workflows for semantics, and
`url`/`url_out` stated once with a link to the Lambda functions page. Promote the two
Earth Search anecdotes out of "Additional considerations" into a heading that says
what they are (e.g. "When Batch overhead dominates"). Fix "Interestly"; this page and
its sibling still need their deferred full audit (DOCS_PLAN carry-over) — do it during
this rewrite.

**Batch infrastructure** (was `components/tasks/batch.md`). The CloudFormation
resource set, compute environments, Spot, launch templates, IAM, queues. Restructure
so "declare a Batch task" comes first and the operational hazards ("Observed issues" +
blue/green playbook, the back third) become a clearly-bounded "Updating Batch
resources safely" section a first-time reader can skip. Tone pass to match neighbors.

**Feeders** (`components/feeders/index.md`, moved to guides). Content is already
guide-shaped and good. Trim the payload-validation restatement to a link into the
payload schema page.

**Deployment** (was `cirrus/40_config-deploy.md`). Owns: the stack table, the full
parameter table, a new consolidated `CIRRUS_*` env var table, quotas/limits, deploy
permissions, and a new "Scaling and throughput" section that absorbs the
queue-splitting tip from `95_tips_and_tricks.md` (killing that page) and states the
process Lambda's reserved-concurrency-16 ceiling and where to raise it, plus Batch
`MaxvCpus`/`MinvCpus` pointers. Keeps its "the quickstart is the walkthrough" framing.

**Monitoring & troubleshooting** (was `cirrus/80_monitoring.md`). Already the
strongest guide. Absorbs `cirrus/50_operation.md`'s bulk-rerun content as a
"Rerunning payloads" section — using the corrected line-by-line loop, killing the
stale `xargs` example with the page. The rerun state-eligibility rule appears as a
link to the payload schema, not a fourth table. Annotate the event-type table's
lookalike pairs (`RECORD_EXTRACT_FAILED` vs `NOT_A_PROCESS_PAYLOAD`).

**Upgrading to 2.0** (`cirrus/85_upgrading.md`, unchanged). Its internal
operator/CLI/library split is the honest audience partition and stays. Its eventual
retirement rides on the 1.x version-selector decision (below).

**Payload schema** (was `cirrus/30_payload.md`, moved to Reference). The canonical
contract page: field tables, ID format and derivation, validation rules, process
definition, `replace` semantics (the one telling of the rerun rule), upload options,
`collection_matchers`. Add the code-map constraint that workflow names must not
contain underscores next to the ID format (currently only on the StateDB page).

**State database** (`cirrus/70_statedb.md`, near-unchanged). Keeps the CLAIMED
mechanism as its unique depth; other pages link here for "why CLAIMED exists."

**Payload bucket** (`cirrus/75_payload_bucket.md`, unchanged). Site's best page.

**HTTP API** (was `cirrus/78_api_endpoints.md`). Unchanged in content. The summary
page `components/functions/api.md` is deleted; the Lambda functions page's `api`
section carries one paragraph plus a link here.

**Lambda functions** (merge `components/functions/{index,api,process,update-state,
pre_batch,post_batch}.md` into one page, five sections). The five pages total ~190
lines; one page removes the index stub and gives `url`/`url_out` and the
state-transition behavior a single citable home. Section anchors preserve deep links.

**Using the CLI** (merge `cli/00_intro.md` + `cli/01_install.md` + `cli/02_auth.md` +
`cli/03_deployments.md`). One setup page: install (one blessed incantation; pipx,
with `uvx` as the ephemeral variant), credentials (including what IAM permissions a
CLI user needs and the `CIRRUS_CLI_IAM_ARN` assume-role mechanism), and deployment
discovery with a real SSM example — the pointer parameter at
`/cirrus/deployments/<name>` and the parameter set under `/deployment/<name>/`,
introduced alongside `cirrus list-deployments`. Explain the `mgmt` alias and prefix
matching at first use. This also retires the conversational register flagged as
DOCS_PLAN carry-over.

**Command reference** (`cli/reference.md`, generated, unchanged).

**Common CLI workflows** (`cli/04_commands.md`, near-unchanged). The canonical
command tour; already carries the corrected rerun loop. Consider adding
`invoke-lambda` to the debugging scenarios.

**Library API** (six generated pages, unchanged) — except `api/errors.md` gains the
missing intro paragraph, and its nav title should distinguish itself from nothing;
the real title fix is renaming `api/deployment.md`'s nav entry to "Deployment class"
(or "cirrus.management.deployment") to break the collision with the Deployment guide.

**Deleted outright**: `components/index.md` (taxonomy lives in concepts),
`cirrus/95_tips_and_tricks.md` (tip absorbed by Deployment),
`cirrus/50_operation.md` (absorbed by Monitoring), `components/workflows/index.md`
and `components/functions/index.md` (folded), `components/functions/api.md`
(subsumed), `cirrus/20_arch.md` and `cirrus/10_intro.md` (merged into concepts).

### Disposition summary

| Current page | Fate |
| --- | --- |
| index.md | Keep; re-point cards |
| cirrus/10_intro.md | Merge → How Cirrus works |
| cirrus/15_quickstart.md | Keep; collapse LocalStack duplication |
| cirrus/17_end_to_end.md | Slim → Follow a payload through (or fold into quickstart) |
| cirrus/20_arch.md | Merge → How Cirrus works |
| cirrus/30_payload.md | Move → Reference: Payload schema |
| cirrus/40_config-deploy.md | Rework → Deployment (absorbs tips page, gains env-var table + scaling section) |
| cirrus/50_operation.md | Delete; content → Monitoring & troubleshooting |
| cirrus/70_statedb.md | Keep |
| cirrus/75_payload_bucket.md | Keep |
| cirrus/78_api_endpoints.md | Keep → Reference: HTTP API |
| cirrus/80_monitoring.md | Keep; absorb reruns |
| cirrus/85_upgrading.md | Keep |
| cirrus/95_tips_and_tricks.md | Delete; tip → Deployment |
| components/index.md | Delete |
| components/feeders/index.md | Move → guides: Feeders |
| components/functions/* (6 pages) | Merge → Reference: Lambda functions |
| components/tasks/index.md | Move/retitle → guides: Tasks |
| components/tasks/batch.md | Retitle → Batch infrastructure; restructure + tone pass |
| components/workflows/index.md | Fold → Workflows |
| components/workflows/definitions.md | Rework → Workflows (canonical homes added) |
| components/workflows/chaining.md | Keep |
| components/workflows/batch.md | Retitle → Batch workflow structure; full audit |
| cli/00–03 (4 pages) | Merge → Using the CLI |
| cli/04_commands.md | Keep (cookbook) |
| cli/reference.md | Keep (generated) |
| api/* (6 pages) | Keep; add errors intro; rename deployment nav entry |
| about/* (3 pages) | Keep |

## Upstream sources (note, don't touch)

- Docstring quality for the Library API pages: already tracked in
  `DOCSTRING_GAPS.md` for a follow-up code PR (also removes
  `docstring_options.warnings: false`).
- Click help text feeds `cli/reference.md`; any command whose generated description
  reads poorly is a `management/commands/*` docstring/help fix, same follow-up PR.
- `CONTRIBUTING.md` / `CHANGELOG.md` / `LICENSE` are snippet-included; edits happen at
  the repo root, not in docs/src.

## Maintainer decisions carried forward

Consolidated from OPEN_QUESTIONS.md and DOCS_PLAN.md so both files can be retired:

1. **1.x visibility in the version selector** (DOCS_PLAN 5.4): hand-add 1.x entries to
   `versions.json` on gh-pages, or leave 1.x unlisted and rely on the upgrading guide.
   Needed by the first release deploy (`mike set-default stable`).
2. **AWS quota numbers** dropped from the deployment guide (verified-stale list
   preserved in OPEN_QUESTIONS.md git history): restore with verified values, or keep
   the qualitative-with-links approach.
3. **WAFv2/FilmDrop note**: add FilmDrop operational context to the deployment guide,
   or keep it out per the external-repos scope rule.
4. **Three possibly-unintended `api.py` behaviors** documented as-written
   (`urljoin(None)` on missing domainName, literal `items` route shadowing, dropped
   `nextkey` token): fix in code (docs follow-up required) or leave documented.
   Related, found during 3.12: `WorkflowEventManager.timed_out`
   (`src/cirrus/lib/events.py:688-694`) writes its Timestream record with
   `StateEnum.INVALID` while `statedb.set_failed` records FAILED — likely a
   copy-paste bug in the deprecated Timestream path; not documented anywhere.
5. **Scaling claims dropped from the concepts page** (old
   `docs/src/getting-started/intro.md:6-9,52-66`, pre-3.1 git history): "tens to
   millions of items" and the horizontal/vertical scaling section could not be
   verified against code — the only concrete mechanisms found are SQS buffering and
   `ReservedConcurrentExecutions: 16` on the process Lambda
   (`cloudformation/core/functions.yaml:403`). Restore a toned-down, verified
   version in How Cirrus works, or leave out.
6. **STAC-in/STAC-out framing dropped** (old
   `docs/src/getting-started/intro.md:18-29`, pre-3.1 git history): the payload
   schema requires STAC-like items in, but nothing enforces STAC out; the
   "highly-interoperable, metadata-first" language was not traceable to a code
   constraint. Restore reworded if the framing matters, or leave out.
7. **Batch page claims not verifiable in-repo** (3.7/3.8 audits,
   `docs/src/building-pipelines/batch-workflow-structure.md` and
   `batch-infrastructure.md`): kept — `Batch.AWSBatchException` as the
   SubmitJob throttling error name, Spot reclamation as a routine retry cause,
   launch-template version caching at compute-environment creation,
   replace-only compute environments, job-definition revision behavior on
   rollback, job-queue deletion killing jobs, the 50-per-Region compute
   environment/job queue quota, `SpotIamFleetRole` / allocation-strategy
   semantics, NAT data-processing charges (all AWS service behavior, no
   in-repo source), and the two Earth Search anecdotes (Landsat
   `public-c2-notify-v2` timings, Sentinel-2 C1 L2A baseline back-processing
   stats — operator knowledge about a downstream deployment, kept per this
   plan's brief). Confirm or correct from operational experience.
8. **stac-task packaging conventions on the Tasks page** (3.9 audit,
   `docs/src/building-pipelines/tasks.md`): the Docker progression's
   `src/task/task.py` layout, the `CMD ["task.handler"]` Lambda handler
   string, and the Dockerfile examples (`lambgeo/lambda-gdal` etc.) are
   stac-task/Lambda packaging conventions with no in-repo source.
   `stactask.task.Task.handler` exists as a classmethod, consistent with the
   examples, but the exact handler-string resolution was not verifiable here.
   Confirm against a working task repo or stac-task docs.

## Disposition of the planning documents

- **DOCS_PLAN.md**: complete; its value is now historical. Delete from the branch tip
  once this evaluation is accepted — git history preserves it. Its two live
  carry-overs are captured here (batch page audit → the Batch rewrite briefs;
  cli/00_intro register → the Using the CLI merge; docstring PR → Upstream sources;
  5.4 → decision 1 above).
- **OPEN_QUESTIONS.md**: all unresolved items are captured under "Maintainer decisions
  carried forward"; resolved items are recorded in page content or git history. Delete
  alongside DOCS_PLAN.md.
- **DOCSTRING_GAPS.md**: keep — it drives the follow-up code PR and is referenced from
  mkdocs.yml comments.
- **This file** becomes the working plan for the restructure and is itself deleted
  when the work completes.

## Execution plan

Status tracking: living document. Check off tasks as completed; note deviations
inline. Branch: `docs-overhaul` (no PR — commits only).

### Ground rules (carried from DOCS_PLAN.md, which this plan supersedes)

1. **Code is truth; existing docs are untrusted.** Every rewrite task begins by
   reading the relevant source in `src/cirrus/`, `cloudformation/`, or
   `CHANGELOG.md`. Never carry a factual claim forward without verifying it.
2. **Terminology:** "the Cirrus CLI" in prose, `cirrus` for the command; never
   "CLIrrus". `pre-batch`/`post-batch` are Lambda functions, not tasks. States per
   `src/cirrus/lib/enums.py`: PROCESSING, SUCCEEDED, FAILED, INVALID, ABORTED,
   CLAIMED — never COMPLETED. "CloudFormation", "Step Functions", "DynamoDB".
3. **Commit discipline:** one logical unit per commit, conventional-commit style,
   task ID in the message. `mkdocs build --strict` must pass before every commit
   (`uv sync --group docs --extra cli` first so mkdocs-click can import the tree).
4. **Tone:** direct, technical, no filler. Match the payload-bucket page.
5. **Unresolvable claims** are parked under "Maintainer decisions carried forward"
   above with file/line refs — never silently kept or deleted.

### Phase 1 — defect pass

Small, independent commits; worth doing even if later phases are deferred.

- [x] 1.1 Replace the stale bulk-rerun `xargs` pattern in `cirrus/50_operation.md`
      with the corrected line-by-line loop from `cli/04_commands.md`.
- [x] 1.2 Fix `cirrus/20_arch.md` glossary: a workflow can have zero tasks.
- [x] 1.3 Reconcile install commands: `pipx install 'cirrus-geo[cli]'` everywhere
      (align `cli/00_intro.md`'s pinned pip variant). *Deviation: also dropped the
      quick start's venv creation steps — pipx manages its own environment.*
- [x] 1.4 Typos: "One you have" → "Once you have" (`cli/02_auth.md`);
      "Interestly" → "Interestingly" (`components/workflows/batch.md`).
- [x] 1.5 Add the missing intro paragraph to `api/errors.md` (orient
      `cirrus.lib.errors` vs `cirrus.exceptions`; which to raise/catch). Includes
      the note that neither module marks INVALID — that's
      `stactask.exceptions.InvalidInput`.
- [x] 1.6 Rename `api/deployment.md`'s nav title to "Deployment class" to break the
      collision with the Deployment guide.

### Phase 2 — structure pass

Mechanical only: moves, merges, deletions, nav, links. Merged content moves
**verbatim** — no prose rewriting; refinement is Phase 3's job.

- [x] 2.1 File moves/renames to the proposed tree; drop numbered filename prefixes;
      rewrite the `nav:` in mkdocs.yml to the proposed IA. *Deviations: intro and
      arch move as separate pages (`getting-started/{intro,architecture}.md`) until
      the 3.1 merge creates `how-cirrus-works.md`, ordered before Quickstart so the
      vocabulary-first ordering fix lands now. Images moved to a shared
      `docs/src/images/` (used by both Home and the future concepts page). New
      paths: `building-pipelines/`, `operating/`, `reference/`, with the CLI pages
      staying in `cli/` (`04_commands.md` → `cli/common-workflows.md`).*
- [x] 2.2 Concatenation merges: six `components/functions/*` pages → one Lambda
      functions page (preserve section anchors); four `cli/00–03` pages → one Using
      the CLI page; `components/workflows/index.md` → top of the Workflows page.
      *Deviations: merged pages' H1s became H2 sections and their sub-headings
      demoted one level (anchors derive from heading text, so deep-link anchors
      are unchanged). The Workflows page wraps the old definitions content under a
      "Writing workflow definitions" H2 so the folded overview's self-reference
      resolves. The `api.md` paragraph carry-over (2.4) happened here.*
- [x] 2.3 Content-preserving absorptions: `cirrus/95_tips_and_tricks.md`'s tip →
      Deployment page (marked for Phase 3 refinement); `cirrus/50_operation.md`'s
      rerun content → Monitoring page (same marker). *Sections keep their original
      heading text ("Processing queue priority", "Rerun tasks") with
      `TODO(phase-3.11)` / `TODO(phase-3.12)` comment markers; 3.12 should also
      dedupe the query-parameter list the rerun section carried over, and rename
      the section per its brief ("Rerunning payloads").*
- [x] 2.4 Deletions with no content to move: `components/index.md`,
      `components/functions/api.md` (subsumed by the HTTP API page — carry its one
      orientation paragraph into the merged Lambda functions page). *Deviation:
      deleting `components/index.md` required unlinking two references in the intro
      page, including removing the "Components" bullet from the persona reading
      list — content 3.1 deletes anyway.*
- [x] 2.5 Redirects for moved paths within the new site version: propose an approach
      (likely mkdocs-redirects) and get maintainer approval before adding the
      dependency; otherwise document the decision to skip. *Decision (2026-08-08):
      skip — no dependency. Old URLs under previously-deployed mike versions keep
      working; breakage is limited to `/latest/`–`/stable/` deep links and a few
      weeks of stale search results, accepted for this audience. Reversible later:
      the old→new map is reconstructable from git history of this phase. The
      inbound links we control (README.md, also the PyPI page) are re-pointed in
      Phase 4.*
- [x] 2.6 Fix all internal links and anchors; `mkdocs build --strict` clean.
      *Deviation: added `validation.links.anchors: warn` to mkdocs.yml so strict
      builds now fail on broken anchors, not just broken paths. Note for Phase 4:
      README.md links to old published URLs (including the never-existing
      `60_components.html`) and should be re-pointed when the new structure
      deploys.*

### Phase 3 — rewrite pass

One page per task, code-verified per its brief above.

- [x] 3.1 How Cirrus works (merge intro + architecture; delete personas; canonical
      taxonomy; framework-vs-user-code boundary). *Deviations: scaling claims and
      STAC-in/STAC-out framing dropped as unverifiable — parked as decisions 5–6.
      Added verified content not in either old page: workflow dispatch mechanism
      (`${ResourcePrefix}-<name>`, EventBridge prefix match) and a one-clause note
      on the deprecated Timestream event DB (still a box in the architecture
      diagram). Earth Search trivia reduced to one "Who uses this" sentence.*
- [x] 3.2 Quickstart: collapse the duplicated LocalStack narrative; add time/cost
      expectations; exit codes become a link. *Deviations: enabled
      `pymdownx.tabbed` + `content.tabs.link` in mkdocs.yml (site-wide extension,
      needed for the per-step AWS/LocalStack tabs). Time stated as a 10–15 min
      estimate (derived from step count, not measured); cost stated qualitatively
      with the NAT-gateway caveat sourced from the Deployment page. All commands
      re-verified against bin/, cloudformation/, and management/ — no factual
      corrections needed. Disabled pymarkdown md031/md046 in pyproject.toml:
      md031's fixer crashes and md046 false-positives on pymdownx tabbed
      content.*
- [x] 3.3 Follow a payload through: slim to narrative; fold into Quickstart instead
      if it lands under ~80 lines. *Landed at 106 lines — kept as its own page.
      Submit-a-payload walkthrough removed (quickstart step 6 covers it); all
      per-command flag prose replaced with cookbook/reference links; kept the
      unique material (validation contrast, `get-state` 60 s backoff, worked
      state-record JSON — verified against statedb.py and deployment.py).*
- [x] 3.4 Payload schema: canonicalize the `replace`/rerun rule; add the
      no-underscores-in-workflow-names constraint beside the ID format.
      *Rule derived from `payload_manager.py` `process()` + `statedb.py`
      `claim_processing` and stated per state, including the two cases the old
      prose left implicit: `INVALID` is skipped by default, and `PROCESSING`
      stays blocked even with `replace` (DynamoDB condition). Old `#replace`
      anchor renamed to `#the-replace-field-and-reruns`; no inbound `#` links
      existed. The stale `cirrus.lib.errors.InvalidInput` reference in
      `update_state.py:20-23` is already covered by the coverage-gaps note.*
- [x] 3.5 Workflows: canonical homes for naming, ErrorPath/CausePath, retry pattern,
      payload-size ceiling; "Design guidance" heading over the best-practices items.
      *Deviations: payload-size ceiling stated as the code-enforced
      `MAX_PAYLOAD_LENGTH = 120000` bytes (`payload_manager.py:38`), with AWS's
      248 KiB EventBridge limit cited only as the motivation the code comments
      give. Added previously-undocumented verified facts: FAILED-vs-INVALID
      decided by exact error-name match in `update_state.py`, TIMED_OUT mapped
      to FAILED, and `states:StartExecution` scoped to `${ResourcePrefix}-*`.
      Error/cause read off the EventBridge event envelope, not "the Fail state"
      as the old prose had it.*
- [x] 3.6 Feeders: trim the payload-validation restatement to a link. *Two
      restatements trimmed (the "Payload validation" subsection and the
      ID-derivation recap after the worked example), both replaced with links to
      the payload schema page (`#id-format`). Adjacent claims re-verified
      against utils.py, payload_manager.py, and cloudformation/core — no fixes
      needed.*
- [x] 3.7 Batch workflow structure: full deferred audit; single retry-JSON instance
      linking to Workflows; promote the Earth Search anecdotes under a named heading.
      *Deviations: fixed a bug in the worked ASL example — the `Fail` state used
      static `Error`/`Cause` with JSONPath strings, which ASL treats as literals;
      now `ErrorPath`/`CausePath`. Replaced the example's YAML `!GetAtt` intrinsics
      (invalid inside a JSON ASL document) with placeholder ARNs. Retry semantics
      and the `url`/`url_out` contract reduced to links to their canonical homes.
      In-repo-unverifiable claims parked as decision 7.*
- [x] 3.8 Batch infrastructure: restructure (declare-first, hazards into a bounded
      "Updating Batch resources safely" section); tone pass; verify against
      templates. *Deviations: IAM section rewritten around the instance-role /
      job-role (`JobRoleArn`) split per CHANGELOG v0.7.0, which also removed the
      builtin `BatchServiceRole` — the page now recommends omitting
      `ServiceRole`. Added the previously-unstated fact that Cirrus declares no
      Batch resources itself (verified against cloudformation/). Dropped the
      hedged "SubmitJob 30KiB" and "50/sec API limit" numbers as unverifiable;
      trimmed the 26-type Spot instance list to three illustrative entries.
      AWS-behavior claims kept on this page parked under decision 7.*
- [x] 3.9 Tasks: add the logging contract and the
      `stactask.exceptions.InvalidInput` statement; fold the one-bullet list.
      *Deviations: logging contract verified against `cirrus/lib/logging.py`
      (five reserved parent loggers, `CIRRUS_LOG_LEVEL`, adapter extras `id` /
      `stac_version` / `aws_request_id`, parent-propagation disable). The
      Docker progression's stac-task packaging conventions (`task.handler`
      handler string, Dockerfile examples) are external conventions with no
      in-repo source — kept as illustrations, parked as decision 8.*
- [x] 3.10 Using the CLI: rewrite the merged page (one install incantation; CLI-user
      IAM permissions + `CIRRUS_CLI_IAM_ARN`; deployment discovery with a real SSM
      example and `cirrus list-deployments`; explain `mgmt`/prefix matching).
      *Deviations: precedence corrected mid-review — the deployment's
      `CIRRUS_CLI_IAM_ARN` parameter wins over `--iam-arn`
      (`deployment.py:73`, env value first, flag is the `.get()` fallback);
      the subagent's draft had it backwards. `CIRRUS_CLI_IAM_ARN` described as
      optional — it is not among the parameters
      `cloudformation/cli/ssm_parameters.yaml` creates. Dropped the old
      page's deprecated `cirrus-mgmt` PyPI digression. Permissions stated as
      capabilities traced from management source, not a policy document.*
- [x] 3.11 Deployment: env var table, quotas, "Scaling and throughput" section
      (queue-splitting tip refined, reserved-concurrency-16 ceiling, Batch knobs).
      *Deviations: env var table covers all 13 `CIRRUS_*` vars found by source
      sweep, with `CIRRUS_CLI_IAM_ARN` as a pointer to Using the CLI
      (orchestrator cross-checked the sweep — no misses). Stack and parameter
      tables re-verified against main.yaml — already accurate. Queue-splitting
      rewrite notes `ScalingConfig.MaximumConcurrency` is not in the in-repo
      template (illustrative YAML labeled as such). No quota numbers restored,
      per decision 2.*
- [x] 3.12 Monitoring & troubleshooting: refine the absorbed rerun section (rule by
      link, not table); annotate the lookalike event-type pairs.
      *Deviations: found and fixed a second broken `xargs` rerun pipe this page
      carried (1.1 only fixed the operations page's copy). Corrected the
      `ALREADY_INVALID` row (replace applies) and split FAILED/TIMED_OUT/INVALID
      by `update_state.py`'s actual error-type routing, noting `TIMED_OUT` is an
      event type only — the state database records FAILED. Updated the
      cookbook's inbound `#rerun-tasks` anchor to `#rerunning-payloads`.
      Timestream oddity found during verification appended to decision 4.*
- [x] 3.13 Small cross-links: chaining → payload schema `chain_filter`; consider
      `invoke-lambda` in the cookbook's debugging scenarios. *Both done: the
      chaining page links the process-definition table; the cookbook gains an
      "Invoke a Lambda function directly" section (name resolution and response
      handling verified against `deployment.py:267-286`).*

### Phase 4 — cleanup

- [x] 4.1 Delete DOCS_PLAN.md and OPEN_QUESTIONS.md (contents captured above and in
      git history). *Live carry-overs confirmed captured before deletion: batch
      audits (3.7/3.8), cli intro register (3.10), docstring PR (Upstream
      sources), 5.4 (decision 1), OPEN_QUESTIONS items (decisions 2–4). Also
      removed the codespell exclude for DOCS_PLAN.md from
      .pre-commit-config.yaml.*
- [x] 4.2 Re-point the landing page cards at the new nav. *Payloads card
      replaced with Building pipelines (→ Workflows, the section's first page);
      cut the index paragraph duplicating the concepts opening. Also did the
      2.5-deferred README re-pointing: four doc bullets now target the new
      site paths (stable alias, directory URLs) and the architecture image
      path updated to `docs/src/images/`.*
- [x] 4.3 Site-wide internal link + anchor check over the built HTML.
      *Scripted pass over all 31 built pages: every internal href resolves to
      an existing page/asset and every fragment to an element id; zero dead
      links or anchors (root-absolute URLs in 404.html excluded as
      deploy-time-only, as in the Session-3 check).*
- [ ] 4.4 Final verification sweep (grep CLIrrus/COMPLETED/serverless; every state
      enumeration includes CLAIMED; no empty section headers), then delete this file
      in the closing commit.
