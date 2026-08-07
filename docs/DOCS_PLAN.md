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
   After task 4.1, sync with the CLI extra — `uv sync --group docs --extra cli` — so
   mkdocs-click can import the command tree.

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
- [x] 0.2 CLIrrus purge: replace all doc occurrences (`docs/src/cli/*`,
      `components/functions/process.rst`, `cirrus/50_operation.rst`) per terminology rule.
      Rename `RoleSessionName="CLIrrus_iam_session"` in `src/cirrus/lib/utils.py` to
      `"cirrus_cli_session"`; add CHANGELOG entry under Unreleased (behavior-visible in
      CloudTrail session names).
- [x] 0.3 Delete dead weight before conversion: empty examples skeleton
      (`cirrus/90_examples.rst`, `cirrus/examples/e2e-notebook.rst`); `96_deploying.rst`
      (content absorbed by task 2.2); callbacks placeholder **after** checking code — grep
      `src/` for callback support; if implemented, keep a one-line stub and flag task 5.4,
      else delete outright.
      *Callback check: no hits for workflow callbacks in `src/` or `cloudformation/`
      (only click option callbacks; no `waitForTaskToken`/`SendTask*` anywhere) — deleted
      outright, plus the callback bullet in `workflows/definitions.rst` and the callback
      sentence in `workflows/chaining.rst`, which documented the nonexistent feature.*
      *Addendum: `cirrus/65_cloudformation.rst` also deleted — title-only page (2 lines),
      not listed in 0.3 but caught by the no-empty-pages exit criterion. Nothing referenced
      it (main index uses globs).*
- [x] 0.4 Reclassify pre/post-batch pages as functions (file moves + index fixes) so the
      conversion carries the correct taxonomy.
      *`components/tasks/index.rst` deleted — its only entries were the two moved pages,
      and an empty Tasks index would violate the no-empty-pages criterion.*

### Phase 1: mkdocs-material migration
- [x] 1.1 Scaffold: `mkdocs.yml` per Locked decisions (theme, palette, features, plugins,
      nav). Move docs deps: replace the sphinx packages in the `docs` dependency group with
      `mkdocs-material`, `mike`, `mkdocs-mermaid2-plugin` (add `mkdocs-click`,
      `mkdocstrings[python]` now for Session 3). Map existing pages into the target nav —
      pages not yet rewritten slot into their future locations under their current titles.
      *Implementation notes: nav entries for still-RST pages are present in mkdocs.yml but
      commented out, uncommented per 1.2 batch, so every commit passes `mkdocs build
      --strict` (nav can't reference files that don't exist yet). Files keep their current
      paths — the nav maps them into the IA; physical moves can accompany Session 2
      rewrites. Placeholder `index.md` added (replaced in 1.4). About section created now
      via `pymdownx.snippets` includes of CONTRIBUTING.md/CHANGELOG.md/LICENSE; the
      relative `./pyproject.toml` link in CONTRIBUTING.md became a GitHub URL (dangled in
      the site). `mkdocs.yml` excluded from the check-yaml hook (can't parse the
      `!!python/name:` tag needed by the mermaid2 fence; mkdocs validates its own config).
      Sphinx `make -C docs build` is non-functional from this commit (deps swapped); the
      remaining Sphinx machinery is retired in 1.3.*
- [x] 1.2 Convert all remaining `.rst` → `.md` (pandoc first pass; hand-fix admonitions,
      code-block languages, cross-references, images, Mermaid blocks). **Conversion commits
      are content-neutral** — no wording changes, so the diff is reviewable as pure
      transformation. Batch by directory, one commit per batch.
      *Deviations: (1) `cli/` committed alone (no outgoing cross-refs), but the other three
      directories (`cirrus/`, `cirrus/components/`, `components/functions/`) reference each
      other circularly, so they share one commit — intermediate per-directory commits could
      not pass `mkdocs build --strict` with links pointing at not-yet-converted files. Each
      directory was still converted and reviewed as its own agent batch. (2)
      `components/functions/index.rst` deleted rather than converted — pure toctree wrapper;
      the nav lists its five pages directly. (3) Content-neutrality verified mechanically:
      old RST (from git) and new Markdown both rendered to plain text via pandoc and
      diffed — remaining diffs are link-target unwrapping, toctree removal, and reflow
      only.*
- [x] 1.3 Versioned deploys with `mike`; rewrite `.github/workflows/docs-build.yml`; retire
      `docs/update-versions.py`, `static/js/versions-loader.js`, `templates/versions.html`,
      `conf.py`, `Makefile`, `index.include`. Preserve existing published version URLs or add
      redirects where feasible.
      *URL preservation: mike mirrors the existing gh-pages layout — releases → `v<X.Y.Z>`
      dir, main → `main` dir, `dev`/`stable` as symlink aliases (`--alias-type symlink`),
      root redirect via `mike set-default stable` on next release. Old Sphinx-built version
      dirs and `versions.txt` are left untouched on gh-pages; mike only manages versions it
      deployed, so all published URLs keep working. Also retired `index.rst` and the empty
      `extra/` dir; `docs/.gitignore` trimmed to `build`.*
- [x] 1.4 Landing page (`docs/index.md`): what-is paragraph (adapt from README), architecture
      image, card-style quick links to quickstart / architecture / payloads / CLI (mirror
      stac-server's landing page pattern). Verify `mkdocs build --strict` clean and
      spot-check every page against the old Sphinx rendering.
      *Notes: quickstart card points at `cirrus/10_intro.md` ("Getting started with
      Cirrus") until task 2.1 authors the real quickstart — retarget the card then. Added
      `pymdownx.emoji` (stock Material config) for card icons. Spot-check found the
      pymarkdown hook's MD046 consistent-style fix had reverted the chaining-page mermaid
      fences to indented code (silently breaking mermaid rendering); fixed by making
      chaining.md all-fenced. Every built page verified to have an H1 and body content;
      images and version-selector config verified in the rendered HTML.*

**Session 1 exit criteria:** `mkdocs build --strict` clean; `mkdocs serve` shows the full
site in Material with the target nav; no empty pages; no CLIrrus; codespell in CI; version
selector works.

**Session 1 result (2026-08-06): complete.** Strict build clean; full target nav; no empty
pages; CLIrrus gone from docs/src and src (remaining hits are this plan's own rule text and
the CHANGELOG history entry); codespell runs in CI via the pre-commit hook. Version
selector: `extra.version.provider: mike` verified in the rendered HTML; end-to-end behavior
is only observable after the first mike deploy from CI. Verification checklist notes:
the one `COMPLETED` doc hit (cli/04_commands.md:220, legacy-record migration) and the
`${opt:stage}` Serverless hit (components/tasks/batch.md, task 3.3 scope) are reviewed and
intentional; three sampled code examples (migrate `--since-days`/`--dry-run`,
`PayloadBucket.get_*_payload_url`, `chain_filter` JSONPath) verified against source.
Pre-existing empty *section headers* remain on pages whose rewrites are Session-2 tasks
(2.2, 2.3); those without a covering task were recorded in `docs/OPEN_QUESTIONS.md`, then
deleted per maintainer decision (less is more) — 18 headings across 10_intro, 20_arch,
50_operation, feeders/index, and tasks/batch, including parents emptied by the deletions
and a duplicated "Process definition" pair in 50_operation.

## Session 2 — Content correctness and the big gaps (authored in Markdown)

### Phase 2: replace stubs with real content
- [x] 2.1 Quickstart: port `cloudformation/README.md` (305 lines) into
      Getting Started → Quickstart, restructured: overview → prerequisites → bootstrap →
      deploy → minimal workflow test → LocalStack. Verify every command against the templates
      in `cloudformation/`. Link prominently from the landing page.
      *New page `docs/src/cirrus/15_quickstart.md`; landing card retargeted (deferred 1.4
      item). Corrected the README's `cirrus management` to `cirrus manage` (actual Click
      group; alias `mgmt`); documented run-workflow exit codes 0/10/11.*
- [x] 2.2 Deployment guide (Guides → Deployment): CloudFormation as the canonical in-repo
      path (cross-link quickstart); AWS quotas/limits content salvaged from old
      `40_config-deploy` (verify numbers still current against AWS docs where cheap, else
      flag in OPEN_QUESTIONS.md); "Other deployment approaches" — one line + links to the two
      external Terraform repos, nothing more (scope rule). Delete the remaining empty
      `40_config-deploy` headers; "create new project" scaffolding-CLI section is deleted
      (that CLI no longer exists); serverless-era `cirrus.yml` instructions deleted.
      *Deviation: the second Terraform repo is `Element84/terraform-aws-cirrus-processing`
      (the crib-life URL in triage notes 404s; Element84 URL verified live). Dropped quota
      numbers parked in OPEN_QUESTIONS.md; S3 bucket quota corrected 200 → 10,000; WAF line
      deleted (unused in repo). Nav label now "Deployment".*
- [x] 2.3 Monitoring guide: fill the empty sections — StateDB queries via CLI, EventDB /
      Timestream workflow events (verify against `lib/eventdb.py`, `lib/events.py`), Step
      Functions console patterns, CloudWatch log locations per lambda.
      *Timestream EventDB documented as deprecated (DeprecationWarning in events.py) in
      favor of CloudWatch metrics via EnableWorkflowMetrics. Side fix: `--since "10 d"`
      examples on the CLI and operations pages corrected to unspaced `10d` per
      `parse_since`'s regex.*

### Phase 3: correctness against v2.0.0
- [x] 3.1 State database reference: regenerate schema from `src/cirrus/lib/statedb.py`
      (add `input_payload_url`, `output_payload_url`, `claimed_at`; fix `itemids` casing;
      remove/annotate legacy `catalog` alias). Document the CLAIMED state. Trim the
      "What is DynamoDB" primer to a paragraph.
      *Key schema/GSIs verified against the StateTable resource in core/base.yaml, not just
      query code. Timestream event claims moved out of this page's scope (monitoring guide
      owns them).*
- [x] 3.2 Grep all docs for state enumerations; ensure CLAIMED appears wherever states are
      listed (known gap: operations page).
      *Operations page also had wrong rerun semantics: with `replace`, everything except
      PROCESSING reruns (INVALID was missing); without it, only FAILED/ABORTED/CLAIMED/
      no-record run — corrected per `lib/payload_manager.py`. Fixed `--collectons-workflow`
      flag typo.*
- [x] 3.3 Batch guide: full line-audit of the converted batch page (712 lines pre-conversion,
      only skimmed in triage). Remove Serverless-framework content (`${opt:stage}` and its
      explanation); re-verify every config example against `lambda_functions/pre_batch.py`,
      `post_batch.py`, and the CloudFormation workflow templates.
      *All `${opt:}`/`${self:}`/`${env:}`/`#{...}` Serverless syntax replaced with
      CloudFormation parameters/!Sub; job definition example modernized to
      ResourceRequirements; url/url_out contract documented; ContainerOverrides
      instance-profile claim corrected. Batch CFN snippets remain illustrative — no in-repo
      batch template exists.*
- [x] 3.4 Line-audit the payloads guide against `src/cirrus/lib/cirrus_payload.py` and
      stac-task's Payload model; audit workflow definitions + chaining pages against the
      CloudFormation workflow templates and update-state logic. (Skimmed in triage — treat
      as unverified.)
      *Major corrections: `process` is an array (was documented as object);
      `output_options` → `upload_options`; nonexistent `input_collections` and built-in
      `publish` task removed; chaining mechanics rewritten (runs via update-state → process
      queue → process function, not workflow-to-workflow); Fail states need
      ErrorPath/CausePath. Addendum: `components/workflows/batch.md` (not in 3.3/3.4 scope)
      got targeted fixes only — url_out pass-through, OutputPath on lambda:invoke steps,
      terminology intro; its full audit is deferred.*
- [x] 3.5 Upgrading-to-2.0 guide from the CHANGELOG v2.0.0 breaking-changes section: payload
      bucket key reorg, CLI renames, COMPLETED→SUCCEEDED, event field renames, library API
      changes. Organize by audience: operators / CLI users / library consumers.
      *New page `docs/src/cirrus/85_upgrading.md`, nav under Guides. Includes migrate
      command mechanics verified against `management/migration.py`.*
- [x] 3.6 Collapse the duplicate component trees into the single Reference → Components
      section; verify all five lambdas (api, process, update_state, pre_batch, post_batch)
      against `src/cirrus/lambda_functions/` and document each.
      *Physical collapse: `cirrus/components/*` and `cirrus/60_components.md` moved into a
      single `docs/src/components/` tree (functions pages were already there). All five
      function pages rewritten from source; all five lambdas are unconditional in
      core/functions.yaml (the old "2 required / 3 optional" split was stale).*

**Session 2 exit criteria:** no stale Serverless-framework content; state docs match
`enums.py` and `statedb.py`; quickstart executable end-to-end on paper; migration guide
exists; single component taxonomy.

## Session 3 — Generated reference and depth

- [x] 4.1 CLI reference generated via `mkdocs-click` covering the full `cirrus` tree
      including `manage` and `payload` groups. Keep curated command examples as a "common
      workflows" page; delete anything the generated reference now duplicates.
      *New `cli/reference.md` renders the full tree (root, manage×20, payload×3, version).
      `cli/04_commands.md` rewritten as "Common CLI workflows" — scenario examples only;
      per-command listings deleted. The old bulk-rerun example piped NDJSON into a single
      `process` invocation (which enqueues one payload per call); replaced with a
      line-by-line loop. CI docs jobs and local preview need `--extra cli` (backoff/click
      are behind the `cli` extra).*
- [x] 4.2 Library API reference via `mkdocstrings[python]` for `cirrus.lib` (CirrusPayload,
      StateDB, PayloadBucket, events, errors/exceptions) and
      `cirrus.management.deployment`. Docstring gaps become entries in `DOCSTRING_GAPS.md` —
      no code edits in this branch beyond 0.2.
      *Six pages under Reference → Library API. `show_if_no_docstring: true` renders
      undocumented public symbols signature-only. Deviation: griffe's docstring-parser
      warnings (malformed existing docstrings) would fail `--strict`, so
      `docstring_options.warnings: false` is set in mkdocs.yml; `DOCSTRING_GAPS.md` records
      every missing/malformed docstring and says to remove that option in the follow-up
      code PR.*
- [x] 4.3 Cirrus API endpoints: enumerate from `src/cirrus/lambda_functions/api.py`; document
      request/response shapes.
      *New `cirrus/78_api_endpoints.md`: 5 routes, path handling, query params, response
      shapes, error behavior, exposure per `core/api.yaml` (GET-only REST API, no auth,
      `dev` stage). Review corrections: /stats is enabled in a default main-stack deploy;
      items responses omit the `nextkey` token (handler drops it); sort params are
      items-only. Three possibly-unintended api.py behaviors parked in OPEN_QUESTIONS.md.
      Side fix: `functions/api.md` spaced `10 d` example → `10d`.*
- [x] 5.1 Feeder guide with at least one complete worked example (SNS→SQS subscription
      pattern and a minimal Python feeder publishing a valid payload).
      *`components/feeders/index.md` rewritten from process-lambda/CloudFormation source.
      No SNS subscription to the process queue exists in-repo, so the SNS→SQS snippet is
      labeled illustrative; direct `sqs:SendMessage` documented as the template-backed
      path. Corrects the old page's nonexistent "process topic" claim.*
- [x] 5.2 End-to-end example: deploy via quickstart → submit payload → track state → inspect
      output. Plain doc page unless a notebook is clearly more maintainable.
      *Plain page `cirrus/17_end_to_end.md`, nav under Getting Started after Quickstart
      (page was not in the locked IA; nav deviation noted). All flags verified against the
      Click source. Documents that `process` does no client-side validation (only
      `run-workflow` does) and `get-state`'s 60 s backoff.*
- [x] 5.3 Callbacks doc if 0.3 found implemented functionality.
      *Moot per 0.3: no callback support found in code — nothing to document unless
      that changes. Checked off as N/A, 2026-08-07.*
**Session 3 result (2026-08-07): complete except 5.4 (maintainer decision).** Generated
CLI and library API references build clean; endpoints, feeder, and end-to-end pages
authored from source. Wrap-up verification: strict build clean; no CLIrrus; grep hits for
COMPLETED/serverless reviewed-intentional; every state enumeration includes CLAIMED; no
empty section headers; no orphaned pages (nav↔disk 1:1); site-wide internal link + anchor
check over the built HTML found zero dead links (404.html's root-absolute URLs are
deploy-time-only, expected). Code examples validated against source this session include
run-workflow exit codes (deployment.py:326-332), the feeder SQS/SNS extraction path
(utils.py:219-236), and /stats gating (main.yaml EnableWorkflowMetrics wiring). Addendum
outside task scope: `95_tips_and_tricks.md` still carried Serverless-era `cirrus.yml`
config that evaded the checklist grep (the literal word never appears) — rewritten in
CloudFormation terms against core/functions.yaml.

## Remaining work (intentionally deferred)

- **Docstring follow-up code PR** (from 4.2): fix everything in `docs/DOCSTRING_GAPS.md`,
  then remove `docstring_options.warnings: false` from mkdocs.yml so docstring
  regressions fail the docs build.
- **Task 5.4** below: 1.x visibility in the version selector — maintainer decision due by
  the first release deploy.
- **OPEN_QUESTIONS.md**, all needing maintainer decisions: restored-or-dropped AWS quota
  numbers (task 2.2); optional WAFv2/FilmDrop note; three possibly-unintended
  `api.py` behaviors documented as-written (urljoin(None), literal `items` route
  shadowing, dropped `nextkey` pagination token).
- **Full audit of `components/workflows/batch.md`** (deferred in 3.4 — only targeted
  fixes applied).
- **`cli/00_intro.md` register**: content is accurate but conversational
  ("And that's it!"); never rewritten in any session. Candidate for a light prose pass.

- [ ] 5.4 Decide 1.x visibility in the version selector (maintainer decision,
      2026-08-07): the dropdown lists only mike-managed versions from `versions.json`;
      old Sphinx-built 1.x dirs keep their URLs but won't appear in it. Options:
      hand-add 1.x entries to `versions.json` on gh-pages (lighter touch), or leave
      1.x unlisted and rely on the upgrading guide. Decision needed by the first
      release deploy (when `mike set-default stable` runs). Writing new 1.x docs was
      considered and rejected — docs are authored for 2.0 only; legacy notes appear
      in pages only where 2.0 code itself carries compat behavior.

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
