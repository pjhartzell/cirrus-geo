# Open questions

Unresolved items parked during the docs overhaul (see DOCS_PLAN.md). Each needs
a decision — fill with verified content or delete — rather than silent
retention.

## AWS quota numbers dropped from the deployment guide (task 2.2, 2026-08-06)

The old `40_config-deploy` quotas section carried specific numbers that could
not be verified as current, so the rewritten page
(`docs/src/cirrus/40_config-deploy.md`, "AWS service quotas and limits")
states them qualitatively with links to the AWS quotas pages instead. Dropped
numbers, should anyone want to restore/verify them:

- Step Functions `StartExecution` token bucket 2,500 / refill 300 per s and
  `GetExecutionHistory` bucket 2,000 / refill 100 per s (old page lines
  25–28): current AWS docs show different values (e.g. 1,300/300 and 400/20
  in major regions) — numbers have drifted and vary by region.
- EC2 "Running On-Demand P instances: 64" (old line 29): narrow, likely
  stale, and unclear relevance to Cirrus's Spot-based Batch usage.
- EC2 Spot request default of 5 per instance type (old line 30): actual
  mechanism is per-family vCPU quotas, not a flat request count.

Deleted outright as wrong or inapplicable (not parked, just noted): WAF
Classic 200 rules/region (WAF is unused anywhere in `cloudformation/` or
`src/`); "no limit on Spot vCPUs" (contradicted by current AWS docs); S3
bucket quota corrected 200 → 10,000 in the page.

## Code discrepancies surfaced by the Session 2 audits (2026-08-06)

Not documentation decisions — code-side items the docs deliberately avoid
depending on:

- `src/cirrus/lambda_functions/update_state.py:21` lists
  `"cirrus.lib.errors.InvalidInput"` in `INVALID_EXCEPTIONS`, but no such
  class exists in `src/cirrus/lib/errors.py` (only
  `stactask.exceptions.InvalidInput` is real). The payloads guide names no
  specific import path for the invalid-input exception because of this.
  Needs a code fix or an intentional-compat note.
- stac-task's `collection_matchers` process-definition field (the
  replacement for the deprecated `upload_options.collections`) is validated
  for mutual exclusivity but its shape is not documented anywhere in
  cirrus-geo and has no in-repo usage to derive from. The payloads guide
  notes the deprecation but does not document `collection_matchers`'
  structure — needs either a stac-task doc link or a verified example.

(The pre-existing empty section headers recorded here during Session 1 were
deleted per maintainer decision, 2026-08-06.)
