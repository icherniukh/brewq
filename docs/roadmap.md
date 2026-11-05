# Design and stabilization roadmap

Brewq answers: “What does Homebrew know about this package/query, and what
should I trust?” Its scope is name/description search, comparison using visible
install counts, and richer installed-package inspection. Install volume is a
comparison signal, not proof of quality. Keep the interface small and the data
and failure modes understandable.

This document describes direction and release gates. **Live work status lives
in Beads**; the first-public-release gate is `brewq-m1-release`. Run `bd ready`
and `bd list --status=in_progress`. The [README](../README.md) describes current
behavior, including known inconsistencies. Historical snapshots and the closed
`brewq-4oc` stabilization milestone do not establish readiness of a new release.

## First public release boundary

The November release cut separates a finite public 0.x release from optional
polish and new product ideas. Beads owns membership, priorities, dependencies,
and completion evidence; this is the rationale, not a second task inventory.

| Milestone | Purpose | Release relationship |
| --- | --- | --- |
| M1 — `brewq-m1-release` | Legal/provenance and privacy clearance; settled CLI contract; background-refresh control; honest result limits; one installation path and factual public docs; final artifact verification. | **Release after M1.** This is the only first-public-release gate. |
| M2 — `brewq-m2-ux` | Everyday terminal UX: responsive layout, readable cells and non-color cues, browsing consistency, optional pager, and presentation polish. | Post-release improvements; known limitations must be disclosed, not silently treated as fixed. |
| M3 — `brewq-m3-value` | Select useful query/metadata/completion additions from feedback; automate verification and consider another distribution channel. | Independently releasable after M1; does not require every M2 item first. |
| M4 — `brewq-m4-explore` | Parked experiments, evidence-gated performance work, and personal workflow ideas. | No release commitment. Existing product boundaries still apply. |

At the owner's explicit request, a narrow zsh-completion slice was brought
forward: commands/options derive from argparse, fields from shared registries,
and package names from the validated user snapshot only. It does not refresh,
initialize a seed, reconcile inventory, or integrate with `brew`; broader shell
and suggestion work remains separate. This does not add a release gate.

M1 does not require a GIF, a pager, a palette redesign, autocomplete, more query
modes, CI, or a Homebrew tap. One concrete versioned installation route is enough;
the initial target is a release wheel installed with `uv tool install`, with the
exact artifact location settled in Beads before publication. Registry availability
and ownership must be verified if PyPI is chosen instead. Layout imperfections
can ship as documented M2 limitations; personal-data leakage and missing legal
clearance cannot.

The final task, `brewq-release-gate`, explicitly depends on every other M1 task.
It requires the correct version bump before building, full source verification,
inspection of both wheel and sdist, and installation outside the checkout on the
supported Python baseline. Verify the promised entrypoints, seed, private-data
boundary, clean/offline and failure-state behavior, scheduler opt-out, TTY/pipe
contracts, and the actual installation/uninstallation instructions. The current
verification script's checkout and installed-shim checks are useful inputs, not
proof of a newly built public artifact; skipped checks are not release evidence.

The owner has confirmed that the seed must be sanitized and public Git history
cleaned before release. Short-command convenience should remain; collision-aware
`bq` creation is the desired direction, while `brq` is a proposed fallback, not a
settled contract. License choice, the exact history-redaction scope, and the
supported shortcut setup mechanism still need explicit decisions. Record
entrypoint/flag decisions in `brewq-h7m`; do not silently remove aliases or change
defaults. Completing M1 means ready to recommend a first public 0.x release, not
automatic publication or a 1.0 stability claim.

## Release execution plan

Follow this sequence for M1. This is the execution order and safety boundary;
Beads remains the only task/status tracker. Start or resume with
`bd ready --label m1-release`, read the issue, then claim it. Complete each issue
with verification evidence; do not mark a stage finished only because it is
written here. M2/M3 remain post-release and M4 remains parked.

### 1. Preserve a private recovery point

Before changing the seed or preparing a rewrite, inventory local branches, tags,
stashes, worktrees, and staged/unstaged/untracked work. Make and verify a private
Git backup plus a separate backup of uncommitted and untracked files; a Git-only
backup does not capture the dirty working tree. Keep backups and the original
history outside anything intended for publication. Do not reset, clean, stash
away, or overwrite existing work just to prepare the release.

### 2. Sanitize the seed and prevent recurrence

Implement `brewq-seed-paths`: fix the seed builder, cover nested personal paths
and installed state with regressions, then regenerate or sanitize and re-encode
the seed. Remove actual builder-specific values without blindly damaging valid
upstream examples. Preserve package identity, analytics, and cask binary data.
Inspect the resulting compressed resource, not just a sanitizer test. Historical
copies are addressed in stage 4; changing today's file does not clean history.

### 3. Finish and freeze the small M1 release contract

Continue independent M1 work while privacy fixes are prepared: resolve the
license/notices, implement scheduler opt-out and result-limit disclosure, settle
the cap/installed-filter spellings, and fix query/flag ordering. Keep terminal
height work to a deterministic budget, not an expanded layout project. Settle
`brewq-bqname`, then align packaging metadata and factual public documentation
with one supported install/uninstall route. No GIF, extra registry, tap, or new
query feature is required. Freeze this prepared candidate before the history
cleanup so private text is not reintroduced afterward.

**Short-command direction to validate:** always retain `brewq`; provide `bq`
automatically when that name is unclaimed, without overwriting another tool or
user shortcut. If `bq` belongs to something else, consider `brq` only if that
fallback is approved and unclaimed too. Reuse our own existing shortcut on
reinstall; if neither name is safe, retain `brewq` and give a clear diagnostic.
Treat this as installation/setup work, not a side effect of a package query.

The current `pyproject.toml` declares fixed `brewq` and `bq` console scripts, not
shell aliases or collision-aware setup. Verify a supported mechanism for the
chosen installation route before promising automatic selection. Account for
PATH commands, symlinks, aliases/functions in the supported shell, repeat setup,
and uninstall removing only our own files. Do not silently edit shell startup
files, install both names as a substitute for collision handling, or invent a
conditional package-install hook. If the route cannot support the desired
behavior, report that gap for a concrete decision rather than claim it works.

**Settled flag spellings:** installed-only search uses `-i` / `--installed`;
`-l` is retired rather than kept as an ambiguous shortcut. Both search and `list`
use `-t` / `--top` for explicit positive caps and retain `--limit` as an alias;
no `-n` shorthand is added. This unifies explicit controls without changing the
existing automatic-cap defaults or making `--all` mean unlimited output.

**Installed-view presentation:** the owner brought the narrow-output fix
forward. Both `list` and installed-only search use the configured list columns,
defaulting to name/description; normal search retains its analytics layout.
Bound the name column, favor description context, and retain requested metadata
through explicit columns rather than crowding the default. This is display-only:
TSV keeps full identifiers and values, and cap/sort policies are unchanged.

### 4. Clean public Git history in an isolated copy

Execute `brewq-history-scrub` after the sanitized seed and M1 candidate/docs are
ready. Review and approve the exact redaction/removal map and branches/tags to be
published. Use a disposable rewrite copy, not this dirty working checkout. Keep
private research and the original data in the private recovery backup; do not
blanket-delete archives, Beads, contributor guidance, or the legacy prototype.
Preserve required licensing and provenance, and review affected local feature
branches so later merges cannot reintroduce old private blobs.

Inspect every ref intended for publication and its reachable objects for the
reviewed private material, not only the final file tree. Compare the rewritten
candidate tree with the prepared candidate to catch unintended changes. Record
the reviewed scope and verification evidence. Stop before replacing the working
repository or its refs until that concrete operation is approved. Do not push,
force-push, or expose backup/original refs; remote publication is a separate step.

### 5. Verify the exact release candidate

Run `brewq-release-gate` only after all other M1 work, including history cleanup.
Choose and commit the correct version bump before any release build. Run the
full checks against the cleaned candidate, build and inspect wheel and sdist,
and install outside the checkout on the supported Python baseline. Verify seed
availability/privacy, the decided command/shortcut behavior, offline/cache/config
and inventory cases, scheduler opt-out, TTY/piped/no-color and TSV behavior, and
installation/uninstallation. Recheck both source history and artifacts for private
material after any further edit. Record the candidate revision, version, artifact
hashes, exact results, and disclosed M2 limitations; skipped checks are not passes.

### 6. Release after M1, then take feedback

Once the M1 issues and final gate are verified, the candidate is suitable for a
first public 0.x release. Obtain publication approval, publish only the reviewed
source/refs and artifacts through the chosen route, and smoke-check the published
install instructions. Do not wait for M2 or M3. Keep later refinements independently
releasable instead of turning the optional backlog into another release gate.

## Historical stabilization sequence

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

CLI alignment (`brewq-h7m`, refined by `brewq-cqt`) establishes a compact common
help path and one visible column selector shared by search and list. Extended
column, trending, and cache reference lives in `--full-help`; legacy output
shortcuts remain accepted but undiscoverable for compatibility. `auto` is
configuration-only and ambiguous popularity aliases are rejected. The layout
lab remains available as the explicitly non-product `random` command.

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

### Follow-ups from the historical milestone

Later work is grouped by the public release boundary above. Autocomplete and
README animation remain optional post-release work. Further cache optimization
requires fresh full-path measurements; the recorded sub-100ms search/list results
are not a reason to add another cache representation. Extended metadata and
package-update research remain exploratory. Local hook cleanup (`brewq-tm6`) is
completed tooling work, not a package feature or release guarantee.

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

Table momentum cues emphasize rising TREND values with direction markers and
terminal-theme green, using bold for values at least 2×. Neutral cache footers
keep freshness and repair state visible without competing with query results.
These presentation bands do not change analytics, sorting, or TSV values.

Column control stays within `-c`: an on-demand field reference, all-field
selection, and additive/subtractive edits to the command's configured layout.
The shared registry owns field names and aliases; defaults and compatibility
shortcuts remain intact. Field discovery needs no cache or operational config.

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
