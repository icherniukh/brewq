# Changelog

## 0.12.0

Actions are explicit `+` tokens. `brewq list` searches for list; `brewq +list`
shows the installed inventory. The same rule covers `+update`, `+setup`,
`+config`, and `+completion`.

## 0.11.1

Local wheel contract. There is no public package index or project URL yet.

- Install with `uv tool install <wheel>`, then `brewq +setup` if `bq` is free.
- The package installs `brewq` only. Setup never overwrites a foreign `bq`,
  alias, or function, and it does not create `brq`.
- Uninstall with `brewq +setup --remove`, then `uv tool uninstall brewq`.
  Cache and config live under the XDG cache and config directories and are not
  removed by the package uninstall.
- Search is the root command. `-u` updates the local register. `-R` reverses
  the chosen order and is off unless requested. Terminal height does not limit
  the result count.
- Original code is MIT. The bundled catalog and spell-correction port keep
  their upstream notices in `NOTICE`.
