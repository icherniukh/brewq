> Historical snapshot, archived 2026-09-21. This document is not the current contract or roadmap.
> See the repository README, AGENTS.md, and docs/roadmap.md. Paths and issue status below reflect the original context.

# Roadmap

Goal: finish implementation and cut a usable release within a few days.

## Day 1 - Project Shape and Core CLI

- Create Python package skeleton.
- Implement the redesigned CLI from `docs/cli-design.md`.
- Keep search as the root command, not a public subcommand.
- Keep only the minimal first-release options listed in the CLI design.
- Implement config-backed defaults before finalizing output behavior.
- Implement the universal column system before table rendering.
- Implement result model and Homebrew subprocess boundary.
- Implement cache path/freshness checks.
- Implement name, alias, and description search to replace `brew-discover` / `bsd` without preserving their flags.
- Implement installed listing to replace `brew-installed` / `brew-ll`.
- Add unit tests for config loading, column normalization, argument parsing, and renderer basics.

## Day 2 - Cache and Rendering

- Implement cache rebuild from `brew info --json=v2 --eval-all`.
- Fetch 30-day and 365-day formula/cask analytics.
- Merge analytics into a stable local cache schema.
- Implement lock-protected refresh.
- Implement deterministic config-driven column layout and wrapping.
- Test warm-cache rendering with fixture data.
- Test installed-list rendering with fixture data from `brew info --json=v2 --installed`.

## Day 3 - Fallbacks and Local Install

- Bundle a release-time seed cache for immediate first use.
- Overlay installed state from local Homebrew storage when the seed is used.
- Render stale data immediately and schedule delayed low-load refresh afterward.
- Add useful errors for missing `brew`, invalid cache JSON, and interrupted refreshes.
- Keep `refresh` as optional recovery behavior and `update-cache` as a compatibility alias.
- Add install docs and shell alias docs.
- Validate in a fresh shell.

## Day 4 - Release Candidate

- Add versioning.
- Add `ruff` if useful.
- Add CI or at least a local `make test` equivalent.
- Tag a local release candidate.
- Decide Homebrew tap location and formula strategy.

## Open Decisions

- Whether to show 365-day installs in the default columns or only through `-s 365d` / explicit columns.
- Whether to keep `brew search` as the matching source or search directly in the cache.
- Whether the first public release should be Python-only or include the zsh prototype as an unsupported legacy script.
