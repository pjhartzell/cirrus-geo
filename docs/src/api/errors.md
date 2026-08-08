# Errors and exceptions

Two modules serve different layers. `cirrus.lib.errors` contains errors raised
by the library helpers (payload URL resolution, the events database, the
payload bucket) — catch these when calling `cirrus.lib` code.
`cirrus.exceptions` contains `CirrusError`, the base class for management and
CLI errors; its `exit_code` attribute sets the CLI's exit status. Neither
module marks a payload INVALID — a task raises
`stactask.exceptions.InvalidInput` for that.

## cirrus.lib.errors

::: cirrus.lib.errors
    options:
      show_root_heading: false
      heading_level: 3

## cirrus.exceptions

::: cirrus.exceptions
    options:
      show_root_heading: false
      heading_level: 3
