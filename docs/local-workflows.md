# Local Workflows To Absorb

Source repo inspected: `/Users/ivan/proj/dotfiles-stow`

## Search Aliases

Current aliases:

```zsh
alias brew-discover='brew search --desc --eval-all'
alias bs='brew search'
alias bsd='brew search --desc'
```

`brewq` replacement:

```bash
brewq QUERY
brewq --desc QUERY
```

Implementation note:

- `--desc` should search descriptions in addition to names.
- It should be explicit because description search can be noisy.
- It should still use the same ranking, cache, columns, and JSON output model.

## Installed List

Current aliases/functions:

```zsh
alias brew-installed='brew_installed'
brew-ll() { brew_installed }
```

The existing `brew_installed` function:

- calls `brew info --json=v2 --installed`
- lists formulae and casks together
- shows name and description
- colors formulae and casks differently
- supports `--limit N`
- supports `--analytics`
- supports `--fetch` to fetch missing analytics
- caches per-package analytics under `~/.cache/brew-installed`

`brewq` replacement:

```bash
brewq list
brewq list --analytics
brewq list --analytics --fetch
brewq list --type formula
brewq list --columns name,type,version,description
brewq list --json
```

Implementation note:

- Reuse the main `brewq` cache when possible instead of keeping a separate `brew-installed` cache.
- Keep `--analytics` cache-only by default.
- Require explicit `--fetch` for missing per-package analytics.
- Do not add install/uninstall/upgrade behavior.
