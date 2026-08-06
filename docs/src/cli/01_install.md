# Installing

Built using python [click](https://click.palletsprojects.com/en/stable/) library and included in the broader [cirrus-geo](https://github.com/cirrus-geo/cirrus-geo)
library, you can install the CLI tool on its own or alongside other project
requirements. A standalone CLI installation might look like

``` bash
pipx install 'cirrus-geo[cli]'
```

Another way is to use a more modern tool like `uv` to run specific CLI
commands in an ephemeral environment.

``` bash
uvx --from 'cirrus-geo[cli]' cirrus [COMMAND]
```
