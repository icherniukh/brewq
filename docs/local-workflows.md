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
brewq QUERY TERMS
```

Implementation note:

- Search should cover names, formula aliases, and descriptions using the same ranking, cache, columns, and TSV output model.
- If description matching proves too noisy in real use, treat search-scope controls as a later product decision instead of reintroducing one-off compatibility flags.

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
- uses cached analytics only during normal list rendering
- caches per-package analytics under `~/.cache/brew-installed`

`brewq` replacement:

```bash
brewq list
brewq list --analytics
brewq refresh
brewq list --analytics
brewq list --columns name,type,version,description
brewq list --tsv
```

Implementation note:

- Reuse the main `brewq` cache when possible instead of keeping a separate `brew-installed` cache.
- Keep `--analytics` cache-only by default.
- Require explicit `brewq refresh` before rendering when fresh analytics are needed.
- Do not add install/uninstall/upgrade behavior.
