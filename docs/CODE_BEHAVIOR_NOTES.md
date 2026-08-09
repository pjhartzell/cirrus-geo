# Possibly-unintended code behaviors

Behaviors surfaced by the docs audits (2026-08) that look unintended but are
documented as-written where user-visible. Docs-branch policy is no code
edits, so these are recorded here for follow-up. Each fix is a code change
that requires a docs follow-up where a page is cited.

## api Lambda (`src/cirrus/lambda_functions/api.py`)

- **`urljoin(None)` on missing `domainName`** (`api.py:274-280`). If API
  Gateway supplies no `requestContext.domainName`, `root_url` is `None` and
  `get_root` calls `urljoin(None, ...)`, which raises. Likely dead code for
  real `AWS_PROXY` events; not reachable to verify from docs work.
- **Literal `items` route shadowing** (`api.py:337`). The item-ID path
  segment is matched against the literal string `"items"` to select the
  paginated items route, so a payload whose item-ID segment is literally
  `items` is shadowed and cannot be fetched individually.
- **Dropped `nextkey` pagination token** (`api.py:354-356`). The items route
  discards the `nextkey` continuation token that `StateDB.get_items_page`
  computes; the response body contains only `items`. Clients can still
  paginate by passing the last returned item's `payload_id` as `nextkey`.
  The HTTP API reference (`docs/src/reference/http-api.md`) documents that
  workaround; returning the token may have been the intent.

## Workflow events (`src/cirrus/lib/events.py`)

- **`timed_out` writes its Timestream record as `INVALID`**
  (`events.py:688-694`). `WorkflowEventManager.timed_out` calls
  `statedb.set_failed` (state database records `FAILED`, consistent with
  `update-state`'s documented mapping) but passes `StateEnum.INVALID` to
  `_write_timeseries_record`. Likely a copy-paste error from the `invalid`
  method. Low impact — the Timestream event DB is deprecated — but the
  record written disagrees with the state recorded.
