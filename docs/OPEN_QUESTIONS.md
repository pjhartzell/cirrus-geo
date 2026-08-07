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

Deleted outright as wrong or inapplicable (not parked, just noted): "no
limit on Spot vCPUs" (contradicted by current AWS docs); S3 bucket quota
corrected 200 → 10,000 in the page.

The WAF Classic 200-rules/region line was also deleted, with extra context
(investigated 2026-08-07): WAF appears nowhere in cirrus-geo's
`cloudformation/` or `src/`, but FilmDrop deployments
(`Element84/filmdrop-aws-tf-modules`) front their CloudFront distributions
with WAF — which is almost certainly why the line was in the original
operator quota list (introduced in PR #240, Feb 2024, by Element84). That
suite uses WAF**v2** (`aws_wafv2_*` resources), so the cited WAF *Classic*
quota was stale even for that context. FilmDrop-specific quota guidance
belongs in that repo's docs per the plan's scope rule; restore a WAFv2 note
here only if the maintainers want FilmDrop operational context in the
cirrus-geo deployment guide.

## Code discrepancies surfaced by the Session 2 audits — RESOLVED 2026-08-07

- `"cirrus.lib.errors.InvalidInput"` in `update_state.py`'s
  `INVALID_EXCEPTIONS` is **intentional backward compatibility**, not a bug:
  commit `a68cea1` ("refine InvalidInput exception support") removed the
  class from `cirrus.lib.errors` and in the same change switched the match
  string to the fully-qualified name, so tasks still running against the
  old cirrus-lib (where the class exists in *their* environment) keep being
  classified `INVALID`. The update-state function page now documents it as
  the legacy name.
- `collection_matchers` shape derived from the installed stac-task source
  (`stactask/utils.py` `_find_collection_from_matchers`, `MatcherType`) and
  verified by executing an example against it: ordered list of matchers,
  `{"type": "jsonpath", "collection_name": ..., "pattern": <JSONPath>}` or
  `{"type": "catch_all", "collection_name": ...}`, first match wins. The
  payloads guide now carries the verified example.

## API-lambda behaviors documented as-written, flagged for maintainers (task 4.3, 2026-08-07)

The new endpoints page (`docs/src/cirrus/78_api_endpoints.md`) documents
these code behaviors faithfully; each looks possibly unintended, and a code
change would require a docs follow-up:

- `src/cirrus/lambda_functions/api.py:274-280` — if API Gateway supplies no
  `requestContext.domainName`, `root_url` is `None` and `get_root` calls
  `urljoin(None, ...)`, which raises. Likely dead code for real `AWS_PROXY`
  events; not reachable to verify from docs work.
- `src/cirrus/lambda_functions/api.py:337` — `itemids == "items"` is a
  literal string match, so a payload whose item-ID segment is literally
  `items` is shadowed by the paginated items route.
- `src/cirrus/lambda_functions/api.py:354-356` — the items route drops the
  `nextkey` continuation token that `StateDB.get_items_page` computes; the
  response body contains only `items`. Clients can still paginate by passing
  the last returned item's `payload_id` as `nextkey`, and the page documents
  that workaround, but returning the token may have been the intent.

(The pre-existing empty section headers recorded here during Session 1 were
deleted per maintainer decision, 2026-08-06.)
