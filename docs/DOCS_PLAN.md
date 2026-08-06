# Cirrus-geo Documentation Overhaul — Working Plan (v2, migrate-first)

Status: living document. Check off tasks as completed; note deviations inline.
Branch: `docs-overhaul` (no PR — push commits only).
Basis: docs triage of v2.0.0 site vs. code at `516d43b` (2026-04-22).

## Locked decisions

- **Toolchain: Material for MkDocs** (stock theme, matching stac-server and TiTiler), with
  `mike` for versioned deploys. No custom CSS in this overhaul.
- **Theme config:** light/dark palette toggle; primary color `teal` (single line in
  mkdocs.yml to change later); features: `navigation.sections`, `navigation.top`,
  `search.suggest`, `content.code.copy`; plugins: `search`, `mermaid2`, `mike`.
- **Information architecture (nav):**
  - **Getting Started** — What is Cirrus · Quickstart (CloudFormation) · Concepts &
    architecture
  - **Guides** — Payloads · Workflows · Batch tasks · Deployment · Operations · Monitoring ·
    Upgrading to 2.0
  - **Reference** — Components (functions/tasks/workflows/feeders) · CLI · Library API ·
    State database · Payload bucket · Cirrus API endpoints
  - **About** — Contributing · Changelog · License
- **Scope: cirrus-geo only.** External deployment tooling (filmdrop-aws-tf-modules,
  terraform-aws-cirrus-processing) gets at most a one-line mention + link on the Deployment
  page. Do not document external repos' interfaces.

## Ground rules

1. **Code is truth; existing docs are untrusted.** Every content task begins by reading the
   relevant source in `src/cirrus/`, `cloudformation/`, or `CHANGELOG.md`. Never carry a
   factual claim forward from an existing page without verifying it against code.
2. **Terminology (enforced everywhere):**
   - "the Cirrus CLI" in prose, `cirrus` for the command. The name "CLIrrus" is retired —
     never write it in new content.
   - `pre-batch` and `post-batch` are **Lambda functions**, not tasks. "Task" is reserved for
     stac-task processing units composed into workflows.
   - State names per `src/cirrus/lib/enums.py`: PROCESSING, SUCCEEDED, FAILED, INVALID,
     ABORTED, CLAIMED. Never COMPLETED.
   - "CloudFormation" (capital F), "Step Functions", "DynamoDB".
3. **Commit discipline:** one logical unit per commit, conventional-commit style, plan-task ID
   in the message. Docs must build clean before every commit (`make -C docs build` while on
   Sphinx; `mkdocs build --strict` after task 1.4). A commit that breaks the build is a
   defect.
4. **Tone:** direct, technical, no marketing filler. Match the register of the current
   payload-bucket page (best existing page).
5. **Local preview:** while on Sphinx, `uv sync --group docs && make -C docs build` then
   `python -m http.server -d docs/build/html`. After task 1.4, `mkdocs serve` (live reload).

## Session 1 — Hygiene, deletions, migration

Goal: end this session with a stub-free, modern-looking mkdocs-material site building
locally, containing the existing content (converted, hygiene-fixed, dead weight removed) —
correctness rewrites come next session, authored directly in Markdown.

### Phase 0: mechanical hygiene (on RST — reduces conversion noise)
- [x] 0.1 Run `codespell` across `docs/` and `README.md`; fix all hits (known: monitorig,
      authenticatig, independant, lambada, scalabale, Additonal, compoent, mentined, commmands,
      acesses, databse, extrated, entires, occured, provisoning). Add `codespell` to CI.
      *Deviation: the `docs-mechanic`/`docs-writer` agent types are not registered with the
      session harness; mechanical tasks are delegated to a general-purpose agent on haiku
      with docs-mechanic's rules inlined in the prompt — same model, same constraints.*
      *Note: codespell added as a pre-commit hook (CI runs `pre-commit run --all-files`),
      scoped to `docs/` + `README.md`, excluding `docs/build` and `DOCS_PLAN.md`.*
- [ ] 0.2 CLIrrus purge: replace all doc occurrences (`docs/src/cli/*`,
      `components/functions/process.rst`, `cirrus/50_operation.rst`) per terminology rule.
      Rename `RoleSessionName="CLIrrus_iam_session"` in `src/cirrus/lib/utils.py` to
      `"cirrus_cli_session"`; add CHANGELOG entry under Unreleased (behavior-visible in
      CloudTrail session names).
- [ ] 0.3 Delete dead weight before conversion: empty examples skeleton
      (`cirrus/90_examples.rst`, `cirrus/examples/e2e-notebook.rst`); `96_deploying.rst`
      (content absorbed by task 2.2); callbacks placeholder **after** checking code — grep
      `src/` for callback support; if implemented, keep a one-line stub and flag task 5.4,
      else delete outright.
- [ ] 0.4 Reclassify pre/post-batch pages as functions (file moves + index fixes) so the
      conversion carries the correct taxonomy.

### Phase 1: mkdocs-material migration
- [ ] 1.1 Scaffold: `mkdocs.yml` per Locked decisions (theme, palette, features, plugins,
      nav). Move docs deps: replace the sphinx packages in the `docs` dependency group with
      `mkdocs-material`, `mike`, `mkdocs-mermaid2-plugin` (add `mkdocs-click`,
      `mkdocstrings[python]` now for Session 3). Map existing pages into the target nav —
      pages not yet rewritten slot into their future locations under their current titles.
- [ ] 1.2 Convert all remaining `.rst` → `.md` (pandoc first pass; hand-fix admonitions,
      code-block languages, cross-references, images, Mermaid blocks). **Conversion commits
      are content-neutral** — no wording changes, so the diff is reviewable as pure
      transformation. Batch by directory, one commit per batch.
- [ ] 1.3 Versioned deploys with `mike`; rewrite `.github/workflows/docs-build.yml`; retire
      `docs/update-versions.py`, `static/js/versions-loader.js`, `templates/versions.html`,
      `conf.py`, `Makefile`, `index.include`. Preserve existing published version URLs or add
      redirects where feasible.
- [ ] 1.4 Landing page (`docs/index.md`): what-is paragraph (adapt from README), architecture
      image, card-style quick links to quickstart / architecture / payloads / CLI (mirror
      stac-server's landing page pattern). Verify `mkdocs build --strict` clean and
      spot-check every page against the old Sphinx rendering.

**Session 1 exit criteria:** `mkdocs build --strict` clean; `mkdocs serve` shows the full
site in Material with the target nav; no empty pages; no CLIrrus; codespell in CI; version
selector works.

## Session 2 — Content correctness and the big gaps (authored in Markdown)

### Phase 2: replace stubs with real content
- [ ] 2.1 Quickstart: port `cloudformation/README.md` (305 lines) into
      Getting Started → Quickstart, restructured: overview → prerequisites → bootstrap →
      deploy → minimal workflow test → LocalStack. Verify every command against the templates
      in `cloudformation/`. Link prominently from the landing page.
- [ ] 2.2 Deployment guide (Guides → Deployment): CloudFormation as the canonical in-repo
      path (cross-link quickstart); AWS quotas/limits content salvaged from old
      `40_config-deploy` (verify numbers still current against AWS docs where cheap, else
      flag in OPEN_QUESTIONS.md); "Other deployment approaches" — one line + links to the two
      external Terraform repos, nothing more (scope rule). Delete the remaining empty
      `40_config-deploy` headers; "create new project" scaffolding-CLI section is deleted
      (that CLI no longer exists); serverless-era `cirrus.yml` instructions deleted.
- [ ] 2.3 Monitoring guide: fill the empty sections — StateDB queries via CLI, EventDB /
      Timestream workflow events (verify against `lib/eventdb.py`, `lib/events.py`), Step
      Functions console patterns, CloudWatch log locations per lambda.

### Phase 3: correctness against v2.0.0
- [ ] 3.1 State database reference: regenerate schema from `src/cirrus/lib/statedb.py`
      (add `input_payload_url`, `output_payload_url`, `claimed_at`; fix `itemids` casing;
      remove/annotate legacy `catalog` alias). Document the CLAIMED state. Trim the
      "What is DynamoDB" primer to a paragraph.
- [ ] 3.2 Grep all docs for state enumerations; ensure CLAIMED appears wherever states are
      listed (known gap: operations page).
- [ ] 3.3 Batch guide: full line-audit of the converted batch page (712 lines pre-conversion,
      only skimmed in triage). Remove Serverless-framework content (`${opt:stage}` and its
      explanation); re-verify every config example against `lambda_functions/pre_batch.py`,
      `post_batch.py`, and the CloudFormation workflow templates.
- [ ] 3.4 Line-audit the payloads guide against `src/cirrus/lib/cirrus_payload.py` and
      stac-task's Payload model; audit workflow definitions + chaining pages against the
      CloudFormation workflow templates and update-state logic. (Skimmed in triage — treat
      as unverified.)
- [ ] 3.5 Upgrading-to-2.0 guide from the CHANGELOG v2.0.0 breaking-changes section: payload
      bucket key reorg, CLI renames, COMPLETED→SUCCEEDED, event field renames, library API
      changes. Organize by audience: operators / CLI users / library consumers.
- [ ] 3.6 Collapse the duplicate component trees into the single Reference → Components
      section; verify all five lambdas (api, process, update_state, pre_batch, post_batch)
      against `src/cirrus/lambda_functions/` and document each.

**Session 2 exit criteria:** no stale Serverless-framework content; state docs match
`enums.py` and `statedb.py`; quickstart executable end-to-end on paper; migration guide
exists; single component taxonomy.

## Session 3 — Generated reference and depth

- [ ] 4.1 CLI reference generated via `mkdocs-click` covering the full `cirrus` tree
      including `manage` and `payload` groups. Keep curated command examples as a "common
      workflows" page; delete anything the generated reference now duplicates.
- [ ] 4.2 Library API reference via `mkdocstrings[python]` for `cirrus.lib` (CirrusPayload,
      StateDB, PayloadBucket, events, errors/exceptions) and
      `cirrus.management.deployment`. Docstring gaps become entries in `DOCSTRING_GAPS.md` —
      no code edits in this branch beyond 0.2.
- [ ] 4.3 Cirrus API endpoints: enumerate from `src/cirrus/lambda_functions/api.py`; document
      request/response shapes.
- [ ] 5.1 Feeder guide with at least one complete worked example (SNS→SQS subscription
      pattern and a minimal Python feeder publishing a valid payload).
- [ ] 5.2 End-to-end example: deploy via quickstart → submit payload → track state → inspect
      output. Plain doc page unless a notebook is clearly more maintainable.
- [ ] 5.3 Callbacks doc if 0.3 found implemented functionality.

## Verification checklist (run at end of every session)
- `mkdocs build --strict` passes (Session 1 pre-migration steps: Sphinx build, no new
  warnings).
- `grep -ri clirrus docs/ src/` → only CHANGELOG history entries.
- `grep -ri "COMPLETED\|serverless" docs/` → reviewed, intentional hits only.
- Every state enumeration includes CLAIMED.
- No page contains an empty section header.
- Random-sample 3 code examples per session and validate against code/templates.
- Unresolvable claims are parked in `docs/OPEN_QUESTIONS.md` with file/line refs, never
  silently kept or deleted.
