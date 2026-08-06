# api

The `api` Lambda function serves a read-only HTTP API over the state
database and workflow event metrics. It supports uses like monitoring
dashboards that need aggregate event statistics, and sits outside the payload
flow shown in the [architecture diagram](../../cirrus/20_arch.md) — unlike
the other functions, it never modifies state.

## Endpoints

All endpoints are `GET` and return JSON.

### Root (`/`)

Returns a catalog-style object describing the deployment, with `child` links
to a state summary endpoint for each collections/workflow combination found
in the deployment's root catalog, and a link to the STAC catalog in the data
bucket.

### `/stats`

Returns aggregate workflow-event counts grouped by state, on daily (60 days),
hourly (36 hours), and rolling-hour bases. Counts are read from CloudWatch
metrics when workflow metrics are enabled, falling back to the Timestream
event database; if neither is configured the endpoint returns a 404.

### `/<collections>/workflow-<workflow>`

Returns per-state record counts for the given collections/workflow
combination, filtered by the query parameters below.

### `/<collections>/workflow-<workflow>/items`

Returns a page of state database records for the given collections/workflow
combination, filtered and paginated by the query parameters below.

### `/<collections>/workflow-<workflow>/<itemids>`

Returns the single state database record for the given payload ID.

## Query parameters

- `state`: filter records on a state database state (`PROCESSING`,
  `SUCCEEDED`, `FAILED`, `INVALID`, `ABORTED`, `CLAIMED`)
- `since`: look-back window relative to now — an integer followed by a unit
  suffix `d` (days), `h` (hours), or `m` (minutes), e.g. `10 d`
- `limit`: maximum number of records to return (default 100000)
- `nextkey`: pagination key from a previous `items` response, returned when
  more results are available
- `sort_ascending`: `1` to sort oldest-first (default `0`, newest-first)
- `sort_index`: index to sort by (default `updated`)

Unrecognized query parameters have no effect.
