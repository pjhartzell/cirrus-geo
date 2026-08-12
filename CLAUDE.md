# cirrus-geo project instructions

## Documentation ground rules

These govern all work under `docs/` (carried from the 2026-08 docs
restructure; the full plan is at `git show 1183402:docs/DOCS_EVALUATION.md`).

1. **Code is truth; docs prose is untrusted.** Verify every factual claim you
   add or change against `src/cirrus/`, `cloudformation/`, or `CHANGELOG.md`.
   If an instruction contradicts what the code says, flag it — don't apply it
   blindly. Claims that can't be verified in-repo: ask rather than silently
   keeping or deleting.
2. **Each fact has one home.** Link to the canonical page instead of
   restating: replace/rerun rule → payload schema; workflow naming, retry
   pattern, error capture → Workflows; `url`/`url_out` contract → Lambda
   functions reference; command tour → CLI cookbook (`cli/common-workflows.md`).
3. **Tone:** direct, technical, no filler or evaluative adjectives. Match
   `docs/src/reference/payload-bucket.md`.
4. **Build gate:** `uv sync --group docs --extra cli && uv run mkdocs build
   --strict` must pass before every docs commit. Strict mode validates
   anchors — before renaming any heading, grep `docs/src` for inbound links
   to it.
5. **Code bugs found while verifying docs** go in
   `docs/CODE_BEHAVIOR_NOTES.md`, not worked around in prose. Docstring gaps
   go in `docs/DOCSTRING_GAPS.md`.

## Terminology

- "the Cirrus CLI" in prose; `cirrus` for the command.
- "task" in prose is reserved for the pipeline's processing units:
  user-authored code taking a Cirrus Payload in and returning one out
  (inline, or by S3 `url` reference for payloads too large to pass between
  steps). Tasks are typically built with stac-task — recommended, not
  required; the framework's only stac-task couplings are `CirrusPayload`
  subclassing its `Payload` and `update-state` recognizing
  `stactask.exceptions.InvalidInput`. `pre-batch` and `post-batch` are
  framework Lambda functions, not Cirrus tasks: the workflow author does
  wire them in explicitly as ASL `Task` states around each Batch step, but
  they ship with the core stack and move payloads around rather than
  processing them.
- States per `StateEnum` (`src/cirrus/lib/enums.py`): PROCESSING, SUCCEEDED,
  FAILED, INVALID, ABORTED, CLAIMED. Never COMPLETED (renamed in 2.0).
- Workflow event types (`WFEventType`) are not states — events also fire for
  skips and rejections that leave state untouched (`ALREADY_*`,
  `DUPLICATE_ID_ENCOUNTERED`, `RECORD_EXTRACT_FAILED`,
  `NOT_A_PROCESS_PAYLOAD`). TIMED_OUT exists only as an event type and Step
  Functions status; the state database records a timed-out execution as
  FAILED.
- "CloudFormation", "Step Functions", "DynamoDB".
