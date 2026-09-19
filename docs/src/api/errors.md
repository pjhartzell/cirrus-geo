# Errors and exceptions

Three modules serve different layers. `cirrus.lib.errors` holds the errors the library helpers raise: a payload with no URL to fetch, the events database being disabled, the payload bucket being unconfigured. `cirrus.exceptions` holds `CirrusError`, whose `exit_code` becomes the CLI's exit status, and the two lookup failures the state database raises. `cirrus.management.exceptions` holds the CLI-layer errors, all `CirrusError` subclasses. None of these marks a payload `INVALID`; a task raises `stactask.exceptions.InvalidInput` for that.

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

## cirrus.management.exceptions

::: cirrus.management.exceptions
    options:
      show_root_heading: false
      heading_level: 3
