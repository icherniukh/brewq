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

The September 21 review found a passing verification suite alongside reproducible
trust failures. User-level brewq was 0.3.1 while the checkout was 0.3.2. Presets and
temporary palette flags therefore appeared installed despite removal from source.
Commit `793c774` preserves the reviewed baseline, including column shortcuts,
theme colors, and binary cache loading; it is not a release-readiness declaration.

### First: reliable state and output

P1 work is required for stability. Configuration and cache schema validation
(`brewq-ybw`) must handle malformed values without tracebacks and keep help,
version, and config-path discovery available. Inventory reconciliation
(`brewq-b14`) must account for removals, inventory-only packages, custom roots,
and failed scans. Cache recovery (`brewq-ar7`) must preserve usable analytics
and incomplete-refresh state, repair recent corruption, and render/flush before
best-effort background scheduling.

These workstreams can progress independently. Share explicit data contracts
rather than relying on mutable flags or file age to imply health. Regression
scenarios belong with the fixes.

### Alongside correctness: one usable contract

CLI alignment (`brewq-h7m`) owns concise grouped help and consistency among
option descriptions, accepted values, defaults, config, and TSV. Resolve the
expanded-column/binaries mismatch, explicit/configured `auto`, conditional
analytics insertion, and refresh semantics. Prefer canonical metric names in
errors; evaluate misleading popularity aliases and relocation of the layout lab
without silently changing compatibility.

Documentation consolidation (`brewq-k1m`) establishes three maintained documents:
README for the actual CLI, AGENTS for contributor workflow, and this document for
design and roadmap. Historical material remains explicitly archived. Future
behavior changes update the authoritative reference in the same commit.

### Then: workflow review and artifact verification

The P2 workflow review (`brewq-9nb`) follows correctness and contract work.
Exercise empty/fresh/stale/partial/corrupt caches, install/uninstall transitions,
TTY and piped output, NO_COLOR, custom columns, and config overrides. Turn
findings into Beads issues instead of accepting a green unit-test suite alone.

The P1 release gate (`brewq-4ri`) follows that review. Build and install an isolated
artifact; prove both `brewq` and `bq` entry points, packaged seed availability,
CLI help/option semantics, and TSV behavior. Compare the installed artifact with
the intended source version and replace the user-level installation only after
verification. Re-run the full existing gate, with no unresolved release-blocking
findings. Existing installed-shim checking only tests help exit status and must
be strengthened.

### After the stability milestone

Autocomplete (`brewq-472`), performance work (`brewq-73z`), and README animation
(`brewq-8a8`) are P3 enhancements blocked by the milestone. Extended metadata
(`brewq-cdj`) and package-update research (`brewq-kj3`) are P4 exploratory work;
the latter remains deferred. Local hook reload verification (`brewq-tm6`) is P2
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
