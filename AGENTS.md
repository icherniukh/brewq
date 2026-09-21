# Working on brewq

## Read first

- [README.md](README.md) is the current user-facing CLI/configuration reference.
- [docs/roadmap.md](docs/roadmap.md) owns product rationale, architectural direction,
  stabilization gates, and the historical-document index.
- `docs/archive/` contains superseded snapshots, not current implementation policy.

Keep these three documents maintained. Do not repeat the CLI contract or defaults
in additional guides. Preserve historical decisions through the archive.

## Product boundary

Brewq is a compact, read-only Homebrew query and analytics tool. Keep search at
the root command, installed inspection in `list`, columns as the output extension
point, and TSV as the sole machine-readable format. No package management,
services, Brewfiles, TUI/GUI, or multi-package-manager abstraction.

The baseline sorts by 90-day install volume and displays TREND in the default
table. Changing that display default, removing compatibility aliases, or moving
the random layout lab requires an explicit decision in `brewq-h7m`, not an
incidental documentation edit. Do not restore presets or temporary palette flags.

Keep competitive analysis in historical/internal design material, not public
README or release copy. Preserve `legacy/bsx-prototype.zsh` until replacement
behavior and the separate dotfiles migration are verified.

## Work tracking and commits

Use local Beads. The stabilization milestone is `brewq-4oc`.

```sh
bd prime
bd ready
bd list --status=in_progress
bd show <id>
```

Read acceptance criteria and dependencies before starting; claim the issue when
work begins. Live Beads is authoritative for status. Do not infer status from Git,
timestamps, archived plans, or dashboard snapshots. Do not maintain parallel
Markdown task lists or duplicate GitHub issues.

Priorities: P0 is an emergency; P1 is required for stabilization; P2 is supporting
review/tooling; P3 is post-stability enhancement; P4 is exploratory backlog.
Dependencies gate feedback and final artifact checks.

Preserve unrelated tracked and untracked work. Commit only reviewed changes.
Keep issue completion and evidence with the completing repository commit:

```sh
bd close <completed-id> --reason '<verified outcome>'
bd export -o .beads/issues.jsonl
```

Stage the exported issue snapshot alongside the corresponding code/docs/tests.
The export is a portable issue snapshot, not the live database or a full Dolt
backup. Re-export after changing priorities or dependencies. Do not push or touch
remotes unless explicitly asked. Machine-local agent settings and runtime locks
are ignored and must not become product configuration.

## Runtime and verification

Use mise for runtime management where pins exist. This repository declares
Python 3.12+ and uses uv/uv.lock; do not migrate runtimes or rewrite dependency
policy incidentally.

```sh
uv sync --extra dev
uv run ruff check .
uv run pytest -q
uv run python scripts/verify.py
```

Run full verification before a PR or completion commit changing runtime behavior.
Use focused checks while iterating. Report exact results and unrun release checks.
Beads' generic Go preflight checklist does not apply. A passing existing gate is
not proof of pending artifact and state-boundary criteria in `brewq-4oc`.

Use `uv run brewq` to test the checkout. User-level `brewq`/`bq` may point to an
older installation. Verify a built artifact before replacing installed tools;
never silently test the wrong version.

## Ownership and implementation

Keep Python, argparse, the normalized package model, and the shared column
registry. Refactor incrementally while fixing tracked behavior:

- CLI owns parsing, dispatch, diagnostics, and exit codes.
- Config owns validation and typed defaults; options normalize requests.
- Search policy owns matching, ranking, and limits, without I/O.
- Cache owns versioned snapshots, completeness, refresh, and atomic persistence.
- Inventory owns membership, installed versions, and discovered binary paths.
- Scheduler owns deferred work; its failure must not suppress query output.
- Columns own public field definitions; renderers own table/TSV formatting.

Some boundaries are targets, not implemented guarantees; see the roadmap and
issue evidence. Do not introduce generic helper/utils modules or a framework.
Measure the full production path before further cache-format optimization.
