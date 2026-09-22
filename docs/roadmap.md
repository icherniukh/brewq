# Design and stabilization roadmap

Brewq answers: “What does Homebrew know about this package/query, and what
should I trust?” Its scope is name/description search, comparison using visible
install counts, and richer installed-package inspection. Install volume is a
comparison signal, not proof of quality. Keep the interface small and the data
and failure modes understandable.

This document describes direction and release gates. **Live work status lives
in Beads**, under milestone `brewq-4oc`; run `bd ready` and
`bd list --status=in_progress`. The [README](../README.md) describes current
behavior, including known inconsistencies. Historical snapshots do not override
either source.

## Stabilization sequence

The milestone completed on September 22, 2026. The sections below preserve the
gates and ownership used to reach that state; Beads remains authoritative for
later enhancement work.

The September 21 review found a passing verification suite alongside reproducible
trust failures. User-level brewq was 0.3.1 while the checkout was 0.3.2. Presets and
temporary palette flags therefore appeared installed despite removal from source.
Commit `793c774` preserves the reviewed baseline, including column shortcuts,
theme colors, and binary cache loading; it is not a release-readiness declaration.

### First: reliable state and output

The first P1 implementation slice covers configuration and cache schema
validation (`brewq-ybw`), inventory reconciliation (`brewq-b14`), and cache
recovery (`brewq-ar7`). Malformed state now falls back without blocking help,
version, or config-path discovery. Inventory distinguishes a successful empty
scan from failed roots and keeps installed versions separate from catalog
versions. Cache health is explicit, partial refreshes preserve usable analytics,
and output is flushed before best-effort background scheduling.

These workstreams can progress independently. Share explicit data contracts
rather than relying on mutable flags or file age to imply health. Regression
scenarios belong with the fixes.

### Alongside correctness: one usable contract

CLI alignment (`brewq-h7m`) establishes concise grouped help and consistency
among option descriptions, accepted values, defaults, config, and TSV. The
expanded set includes binaries, `auto` is configuration-only, list analytics
inserts 90d specifically, and ambiguous popularity aliases are rejected. The
layout lab remains available as the explicitly non-product `random` command.

Documentation consolidation (`brewq-k1m`) establishes three maintained documents:
README for the actual CLI, AGENTS for contributor workflow, and this document for
design and roadmap. Historical material remains explicitly archived. Future
behavior changes update the authoritative reference in the same commit.

### Then: workflow review and artifact verification

The P2 workflow review (`brewq-9nb`) exercised empty/fresh/stale/partial/corrupt
caches, install/uninstall transitions, TTY and piped output, NO_COLOR, custom
columns, config overrides, and maintained examples. Its one blocking finding,
an incomplete snapshot labeled only by metadata age, was fixed and regressed.

The P1 release gate (`brewq-4ri`) built and installed an isolated wheel, proved
both `brewq` and `bq`, packaged seed availability, CLI help/option semantics, and
TSV parity, then replaced the stale user-level installation. The full gate now
checks the external installed version and option contract rather than help exit
status alone.

### After the stability milestone

Autocomplete (`brewq-472`), performance work (`brewq-73z`), and README animation
(`brewq-8a8`) are P3 follow-ups after the milestone. Extended metadata
(`brewq-cdj`) and package-update research (`brewq-kj3`) are P4 exploratory work;
the latter remains deferred. Local hook cleanup (`brewq-tm6`) is completed P2
tooling work, not a package feature or release guarantee.

P0 is reserved for emergencies. There is no date-based release promise; behavior
and artifact gates determine readiness.

## Architectural direction

Keep the current language and small module structure. Improve ownership while
fixing behavior rather than starting a rewrite or adding a service framework.

| Boundary | Responsibility and intended contract |
| --- | --- |
| CLI | Parse/dispatch and diagnostics. Help/version/path do not require operational state. |
| Configuration/options | Validate once, return typed settings, normalize requests. |
| Search policy | Pure matching/ranking/filtering/limits, separate from normalization currently in `options.py`. |
| Catalog/cache | Versioned snapshot, metadata age, analytics completeness, atomic writes, refresh ownership. |
| Inventory | Authoritative local membership and installed version, distinct from catalog version; failed scans differ from empty inventory. |
| Scheduler | Typed outcomes and deferred work; output is flushed before scheduling. |
| Columns/rendering | One field vocabulary for help/validation/table/TSV; formatters never discover inventory or fetch data. |

Loading currently combines JSON/pickle selection, normalization, root discovery,
and inventory overlay. Consolidate that orchestration behind one load contract;
separate persistence from refresh policy only as the fixes need it. Retain usable
analytics through partial failures and record repair eligibility independently
from modification time. Audit bootstrap/refresh locks and temporary-file ownership
together.

Avoid redundant per-package filesystem work when selected output does not need
it. Measure complete startup, loading, inventory, matching, and rendering before
optimizing another cache representation. `load_packages()` excludes inventory
overlay; its timing alone cannot establish user-visible performance.

## Decisions to preserve or settle

Search remains the root command, TSV the only script format, and columns the
extension mechanism. Raw 90-day installs remain the default sort. TREND currently
remains in the default table: making it opt-in is a product decision for the CLI
contract issue, not a claim about current behavior. Historical calibration and
rejected popularity/clamp approaches remain in the archive.

Exact matches versus deprecated/disabled hiding, formula/cask grouping, eventual
prototype retirement, and external dotfiles migration remain open decisions.
Semantic/vector search, `info`, `--exact`, `--explain`, `--open`, `list --leaves`,
and a compiled-language rewrite are outside this stabilization milestone.

No install/upgrade/uninstall, services, Brewfiles, TUI/GUI, security scanner, or
multi-package-manager layer is planned. Private competitive research stays out
of README/release copy.

## Historical record

These are preserved snapshots with archive notices. Original paths, statuses,
command examples, and claims can be obsolete; use them for decision provenance,
not execution instructions.

- [Vision](archive/vision.md) and [product specification](archive/product-spec.md):
  rationale, trending history, rejected approaches, and internal context.
- [CLI design](archive/cli-design.md): pre-consolidation command reference.
- [Original roadmap](archive/roadmap.md) and [stack decision](archive/stack.md).
- [Local workflows](archive/local-workflows.md) and [migration](archive/migration.md):
  prototype and external dotfiles provenance; no external cleanup implied.
- [Research analysis](archive/research-analysis.md) and
  [June brainstorm](archive/brainstorm-review-2026-06-06.md).
- [June review](archive/reviews/2026-06-26-top-down-review.md).
- [Cache design](archive/superpowers/specs/2026-06-29-cache-bootstrap-refresh-scheduling-design.md)
  and [implementation plan](archive/superpowers/plans/2026-06-29-cache-bootstrap-refresh-scheduling.md).

The optional [status dashboard](status-dashboard.html) is generated from Beads.
Run `uv run python scripts/update-status-dashboard.py` to refresh its snapshot,
or `uv run python scripts/serve-status-dashboard.py` for live local tracker data.
It does not run tests or establish release readiness.
