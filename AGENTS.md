# AGENTS.md

This repo is the new home for `brewq`: a read-only Homebrew query and analytics tool.

## Orientation

- Canonical vision: `docs/vision.md`
- Directional product spec: `docs/product-spec.md`
- CLI sketch: `docs/cli-design.md`
- Local workflows to replace: `docs/local-workflows.md`
- Historical prototype: `legacy/bsx-prototype.zsh`

`brewq` is not a Homebrew manager. Do not add install, uninstall, upgrade, services, Brewfile, TUI, GUI, or multi-package-manager behavior unless the product direction is explicitly changed.

## Current Framing

The core shape is query + analytics:

- query packages by name and description
- use install counts as a trust/quality signal
- show useful configurable columns
- provide script-friendly output
- list installed formulae/casks with richer metadata
- keep cache behavior visible and reliable

Avoid over-locking undecided details. If a choice is not settled, mark it as `deferred` or `open` instead of turning it into implementation policy.

## Working Rules

- Read the relevant docs before changing code.
- Preserve `legacy/bsx-prototype.zsh` as provenance until replacement behavior is implemented and verified.
- Keep competitor discussion isolated to private/internal docs; do not copy it into public README/release copy.
- Prefer small, reviewable changes.
- Verify factual claims against files or commands.
- Do not push or otherwise touch remotes unless explicitly asked.

## Unsettled Areas

Treat these as open unless a later doc says otherwise:

- exact default search semantics
- `--desc`, `--desc-only`, and `--name-only` final naming
- `--top` versus `--limit`
- exact column presets
- cache update strategy defaults
- trend score
- semantic/vector search
- future Rust/Go rewrite

## Tracker

If beads is initialized here, use `bd ready` and `bd list --status=in_progress` for project status. If not initialized yet, do not assume tracker state from git or file timestamps.
