# Docstring gaps

Inventory of missing and malformed docstrings in the modules covered by the
Library API reference (docs task 4.2). Docs-branch policy is no code edits,
so these are recorded here for a follow-up code PR.

Until fixed, `mkdocs.yml` sets the mkdocstrings-python option
`docstring_options.warnings: false` — griffe's docstring-parser warnings on
the malformed entries below would otherwise fail `mkdocs build --strict`.
Remove that option in the follow-up PR so regressions fail the docs build.

## Missing docstrings

Public symbols with no docstring. All render in the API reference with
signature only (`show_if_no_docstring: true`).

### cirrus.lib.cirrus_payload

- module docstring
- `CirrusPayload.__init__` (the `set_id_if_missing` behavior is undocumented)
- `CirrusPayload.validate`
- `CirrusPayload.set_id`

### cirrus.lib.statedb

- module docstring
- `ValidStateChange` (`__init__`)
- `check_timestamp`
- `StateDB` (class)
- `StateDB.delete_item`
- `StateDB.delete`
- `StateDB.execution_id_from_arn`
- `StateDB.dbitem_to_item`
- `StateDB.payload_id_most_recent_execution_arn`
- `StateDB.payload_id_to_input_payload_url`
- `StateDB.payload_id_to_output_payload_url`

### cirrus.lib.payload_bucket

- module docstring
- `PayloadBucket` (class and `__init__`) and every public method:
  `from_env`, `parse_url`, `upload_oversize_payload`, `upload_batch_payload`,
  `upload_invalid_payload`, `exec_payload_prefix`, `get_input_payload_url`,
  `get_output_payload_url`, `upload_input_payload`, `upload_output_payload`

### cirrus.lib.events

- module docstring
- `WorkflowEvent` (class, `__init__`, and methods `serialize`,
  `from_message_str`, `to_message`, `log_metric_format`, `sns_attributes`)
- `WorkflowMetricLogger.__init__`, `.enabled`, `.add`, `.prepare_batch`
- `WorkflowMetricReader.enabled`
- `WorkflowEventManager.__init__`, `.isotimestamp_now`, and the state-change
  methods `claim_processing`, `started_processing`, `skipping`, `duplicated`,
  `failed`, `timed_out`, `succeeded`, `invalid`, `aborted`

### cirrus.lib.errors

- module docstring (all three exception classes are documented)

### cirrus.exceptions

- module docstring
- `CirrusError`, `PayloadNotFoundError`, `ExecutionNotFoundError` (classes
  and `__init__`s; `CirrusError.exit_code` semantics in particular)

### cirrus.management.deployment

- module docstring
- `now_isoformat`
- `Deployment` (class and `__init__`) and methods: `yield_deployments`,
  `from_pointer`, `from_name`, `get_lambda_functions`, `exec`, `call`,
  `get_payload_state`, `enqueue_payload`, `get_payload_by_id`,
  `get_execution_arn`, `get_execution`, `get_execution_events`,
  `get_workflow_definition`, `invoke_lambda`, `template_payload`,
  `yield_input_payloads`, `fetch_payload`

## Malformed docstrings (griffe parser warnings)

- `src/cirrus/management/deployment.py:295` — `run_workflow` documents a
  `deployment` parameter that is not in the signature (it is `self`).
- `src/cirrus/lib/events.py:227` — confusing continuation-line indentation.
- `src/cirrus/lib/events.py:377` — parameter documented as
  `formatter (Callable[[datetime], str]` (type embedded in the name, unmatched
  paren, not in the signature).
- `src/cirrus/lib/events.py:515` — Args entry
  `See help(WorkflowEventManager.__init__)` is not a `name: description` pair.
- `src/cirrus/lib/events.py:518-520` — Returns entries lack types.
- `src/cirrus/lib/statedb.py:198,250` — Args sections contain the prose line
  "Additional kwargs used by StateDB.query() are also supported here."
- `src/cirrus/lib/statedb.py:477,559,596` — `set_succeeded`, `set_invalid`,
  `set_aborted` document an `execution_arn` parameter not in the signature.
