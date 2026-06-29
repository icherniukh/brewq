# Automatic Cache Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make first-run and stale-cache queries self-healing by loading a bundled seed, overlaying local installed state, and scheduling truthful low-load background refreshes.

**Architecture:** Keep cache selection in `cache.py`, isolate machine-specific inventory in `inventory.py`, and isolate detached work/state in `scheduler.py`. The CLI consumes one `CacheLoad` value, renders first, and then schedules only when the selected source requires it. Refresh returns typed outcomes shared by the manual command and worker.

**Tech Stack:** Python 3.12 standard library, argparse, dataclasses, gzip JSON package data, `fcntl`, pytest, ruff, setuptools.

---

## File Map

- Create `src/brewq/inventory.py`: read Cellar/Caskroom and overlay installed state.
- Create `src/brewq/scheduler.py`: scheduler state, duplicate prevention, detached worker, load gating.
- Create `src/brewq/seed.py`: seed validation, package-resource loading, deterministic generation.
- Create `src/brewq/data/brew-all.json.gz`: generated release seed.
- Create `scripts/build-seed-cache.py`: validated seed-generation entry point.
- Create `tests/test_inventory.py`, `tests/test_scheduler.py`, `tests/test_seed.py`: focused unit coverage.
- Modify `src/brewq/analytics.py`: preserve per-feed failures.
- Modify `src/brewq/brew.py`: add bounded metadata and storage-root calls.
- Modify `src/brewq/cache.py`: typed refresh results and user/seed cache selection.
- Modify `src/brewq/cli.py`: automatic load, disclosure, foreground recovery, post-render scheduling.
- Modify `pyproject.toml`: include compressed package data.
- Modify `tests/test_analytics.py`, `tests/test_cache.py`, `tests/test_cli.py`: regression and integration coverage.
- Modify `AGENTS.md`, `README.md`, `docs/vision.md`, `docs/product-spec.md`, `docs/cli-design.md`: automatic lifecycle contract.

### Task 1: Truthful analytics and refresh outcomes

**Files:**
- Modify: `src/brewq/analytics.py`
- Modify: `src/brewq/cache.py`
- Test: `tests/test_analytics.py`
- Test: `tests/test_cache.py`

- [ ] **Step 1: Write failing tests for feed failures and refresh outcomes**

Add tests that require `_fetch()` to raise `AnalyticsFetchError`, `fetch_all()` to name the failed feed, and `refresh()` to return `FRESH`, `LOCKED`, `COMPLETE`, or `METADATA_ONLY`. The lock test must acquire `refresh.lock` with `fcntl.flock` before calling `refresh()`; the partial test must make `fetch_all()` raise `AnalyticsFetchError("formula_30d", "offline")` and assert that metadata is still written.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `uv run pytest tests/test_analytics.py tests/test_cache.py -q`

Expected: failures because `AnalyticsFetchError`, `RefreshOutcome`, and `RefreshResult` do not exist and `refresh()` returns `None`.

- [ ] **Step 3: Implement typed boundaries**

Implement these public types and behavior:

```python
class AnalyticsFetchError(RuntimeError):
    def __init__(self, feed: str, detail: str):
        super().__init__(f"{feed}: {detail}")
        self.feed = feed
        self.detail = detail

class RefreshOutcome(enum.StrEnum):
    FRESH = "fresh"
    LOCKED = "locked"
    COMPLETE = "complete"
    METADATA_ONLY = "metadata_only"

@dataclass(frozen=True)
class RefreshResult:
    outcome: RefreshOutcome
    path: Path
    analytics_error: str | None = None
```

`analytics._fetch(feed, url)` must convert URL, JSON, and schema errors into `AnalyticsFetchError`. `fetch_all()` must fail on the first incomplete feed. `_do_refresh()` catches only `AnalyticsFetchError`, writes metadata atomically, and returns `METADATA_ONLY`; all six feeds succeeding returns `COMPLETE`. Lock contention returns `LOCKED`; a fresh skip returns `FRESH`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `uv run pytest tests/test_analytics.py tests/test_cache.py -q`

Expected: all focused tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/brewq/analytics.py src/brewq/cache.py tests/test_analytics.py tests/test_cache.py
git commit -m "fix(cache): report refresh outcomes truthfully"
```

### Task 2: Fast local installed inventory

**Files:**
- Create: `src/brewq/inventory.py`
- Modify: `src/brewq/brew.py`
- Test: `tests/test_inventory.py`

- [ ] **Step 1: Write fixture-driven inventory tests**

Build temporary Cellar and Caskroom trees. Formula receipts must include `time`, `source.tap`, and installed versions. Assert that `homebrew/core/ripgrep` maps to `ripgrep`, `acme/tools/widget` maps to `acme/tools/widget`, the newest receipt wins, cask dot-directories are ignored, and unreadable/malformed receipts do not abort other entries.

- [ ] **Step 2: Run the new tests and verify RED**

Run: `uv run pytest tests/test_inventory.py -q`

Expected: import failure because `brewq.inventory` does not exist.

- [ ] **Step 3: Implement the inventory boundary**

Create `InstalledRecord` exactly as follows, then implement `scan(cellar,
caskroom)` and `overlay(packages, records)` with the selection rules in this
task:

```python
@dataclass(frozen=True)
class InstalledRecord:
    name: str
    type: str
    version: str

```

Add `brew.storage_roots()` using two bounded five-second subprocess calls to `brew --cellar` and `brew --caskroom`. Formula canonical names come from receipt `source.tap`; casks use their token directory. Formula versions select the receipt with greatest integer `time`; cask versions select the non-dot directory with greatest `st_mtime`. `overlay()` sets `installed`, replaces `version`, and calls the existing local binary discovery for installed formulae.

- [ ] **Step 4: Verify inventory tests and lint**

Run: `uv run pytest tests/test_inventory.py -q && uv run ruff check src/brewq/inventory.py src/brewq/brew.py tests/test_inventory.py`

Expected: tests pass and ruff reports no errors.

- [ ] **Step 5: Commit**

```bash
git add src/brewq/inventory.py src/brewq/brew.py tests/test_inventory.py
git commit -m "feat(cache): overlay local installed state"
```

### Task 3: Seed generation, validation, and package loading

**Files:**
- Create: `src/brewq/seed.py`
- Create: `scripts/build-seed-cache.py`
- Create: `tests/test_seed.py`
- Modify: `src/brewq/cache.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write failing seed tests**

Tests must cover deterministic gzip bytes, rejection of missing formulae/casks/analytics, package-resource fallback when the user cache is absent, preference for a valid user cache, installed overlay only for seed loads, and `CacheLoad` values whose source is either `"seed"` or `"user"`.

- [ ] **Step 2: Run seed tests and verify RED**

Run: `uv run pytest tests/test_seed.py -q`

Expected: import failure because `brewq.seed` and `CacheLoad` do not exist.

- [ ] **Step 3: Implement seed APIs and cache selection**

Create these data contracts, then implement `validate(data)`,
`encode(data, generated_at)`, and `load_resource()` with the deterministic
validation and encoding rules below:

```python
@dataclass(frozen=True)
class SeedMetadata:
    schema_version: int
    generated_at: int

@dataclass(frozen=True)
class CacheLoad:
    source: str
    packages: list[Package]
    age_seconds: float
```

`encode()` must add `_brewq_seed`, serialize with sorted keys and compact separators, and use `gzip.GzipFile(mtime=0)`. Validation requires non-empty `formulae` and `casks`, all six analytics fields to exist on representative records, schema version `1`, and a positive generation timestamp. `cache.load()` prefers valid user JSON; otherwise it loads the resource, scans local inventory, applies the overlay, and reports seed age from `generated_at`.

Add setuptools package data:

```toml
[tool.setuptools.package-data]
brewq = ["data/*.json.gz"]
```

- [ ] **Step 4: Verify seed tests**

Run: `uv run pytest tests/test_seed.py tests/test_cache.py -q`

Expected: all focused tests pass.

- [ ] **Step 5: Commit code before the generated artifact**

```bash
git add src/brewq/seed.py src/brewq/cache.py scripts/build-seed-cache.py tests/test_seed.py pyproject.toml
git commit -m "feat(cache): load bundled seed data"
```

### Task 4: Detached cross-platform scheduler

**Files:**
- Create: `src/brewq/scheduler.py`
- Test: `tests/test_scheduler.py`

- [ ] **Step 1: Write failing scheduler tests with injected clock/load/spawn**

Cover fresh no-op, seed/stale scheduling, exclusive scheduler lock, one worker for repeated calls, five-minute initial delay, five-minute load retries, 30-minute maximum deferral, one-hour failure cooldown, stale-state recovery, atomic state JSON, and worker mapping of every `RefreshOutcome`.

- [ ] **Step 2: Run scheduler tests and verify RED**

Run: `uv run pytest tests/test_scheduler.py -q`

Expected: import failure because `brewq.scheduler` does not exist.

- [ ] **Step 3: Implement scheduler and worker**

Expose these constants. Implement `schedule_if_needed(load, max_age)` and
`run_worker(now=time.time, sleep=time.sleep, loadavg=os.getloadavg)` with the
state transitions and subprocess contract below:

```python
INITIAL_DELAY = 300
LOAD_RETRY_DELAY = 300
MAX_DEFERRAL = 1800
RETRY_COOLDOWN = 3600
LOAD_LIMIT = 0.75

```

State lives in `refresh-state.json`; scheduling exclusion uses `schedule.lock`. `schedule_if_needed()` uses `subprocess.Popen([sys.executable, "-m", "brewq.scheduler"], start_new_session=True, stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL, close_fds=True)` only for seed or stale loads outside cooldown. The worker holds `schedule.lock`, records state atomically, sleeps and gates on `loadavg()[0] / max(os.cpu_count() or 1, 1)`, then calls `cache.refresh(force=True)`. Its module entry point exits with `run_worker()`.

- [ ] **Step 4: Verify scheduler tests and lint**

Run: `uv run pytest tests/test_scheduler.py -q && uv run ruff check src/brewq/scheduler.py tests/test_scheduler.py`

Expected: all tests pass and ruff reports no errors.

- [ ] **Step 5: Commit**

```bash
git add src/brewq/scheduler.py tests/test_scheduler.py
git commit -m "feat(cache): schedule low-load refreshes"
```

### Task 5: CLI automatic lifecycle integration

**Files:**
- Modify: `src/brewq/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Replace obsolete CLI expectations with failing lifecycle tests**

Require seed-backed search and list to render installed overlays, stale user cache to render before `schedule_if_needed()`, fresh cache to avoid spawning, stderr disclosures to say `refresh scheduled` without instructing users to run a command, TSV stdout to remain raw, and manual refresh to render truthful fresh/locked/complete/metadata-only outcomes. Retain `-r` as an explicit force escape hatch.

- [ ] **Step 2: Run CLI tests and verify RED**

Run: `uv run pytest tests/test_cli.py -q`

Expected: failures because CLI still calls `load_packages()`, requires explicit refresh, and ignores refresh results.

- [ ] **Step 3: Integrate one load-render-schedule flow**

Both `_cmd_search()` and `_cmd_list()` call `cache.load()`, print disclosure from the returned source/age plus scheduler state, render results, then call `scheduler.schedule_if_needed()` after rendering. Missing seed and user cache invokes `cache.foreground_bootstrap(timeout=60)` and retries `cache.load()` once. `_cmd_refresh()` and `-r` switch on `RefreshOutcome`; `LOCKED` and `METADATA_ONLY` never print complete-success language.

- [ ] **Step 4: Verify CLI tests**

Run: `uv run pytest tests/test_cli.py -q`

Expected: all CLI tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/brewq/cli.py tests/test_cli.py
git commit -m "feat(cli): automate cache bootstrap and refresh"
```

### Task 6: Generate and package the release seed

**Files:**
- Create: `src/brewq/data/brew-all.json.gz`
- Modify: `tests/test_seed.py`

- [ ] **Step 1: Generate a current seed**

Run: `uv run python scripts/build-seed-cache.py src/brewq/data/brew-all.json.gz`

Expected: script reports formula count, cask count, generation time, and compressed size; exit code 0.

- [ ] **Step 2: Verify the artifact and built wheel**

Run: `uv build --wheel && uv run python -m zipfile -l dist/*.whl`

Expected: wheel listing contains `brewq/data/brew-all.json.gz`.

- [ ] **Step 3: Run the seed-only functional test**

Run: `BREWQ_CACHE_DIR=$(mktemp -d) uv run python -m brewq.cli ripgrep`

Expected: result output includes `ripgrep`; stderr identifies bundled seed and scheduled refresh; command does not wait for refresh.

- [ ] **Step 4: Commit the generated artifact**

```bash
git add src/brewq/data/brew-all.json.gz tests/test_seed.py
git commit -m "build(cache): bundle release seed"
```

### Task 7: Documentation and full verification

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `docs/vision.md`
- Modify: `docs/product-spec.md`
- Modify: `docs/cli-design.md`

- [ ] **Step 1: Update the current contract**

State consistently that installs include a seed, first use overlays local installed state, stale data renders immediately, refresh schedules after output, and manual `refresh` is only recovery/diagnostics. Remove all normal-flow instructions that say users must explicitly refresh.

- [ ] **Step 2: Run documentation consistency checks**

Run: `rg -n 'run .brewq refresh.|explicit refresh|required.*refresh|Cache not built' AGENTS.md README.md docs src tests`

Expected: no obsolete normal-flow requirement remains; intentional manual-command documentation is narrowly scoped.

- [ ] **Step 3: Run full verification**

Run: `uv run pytest -q && uv run ruff check . && python3 scripts/benchmark.py --iterations 1`

Expected: all tests pass, ruff reports no errors, and every benchmark case reports zero failures.

- [ ] **Step 4: Run beads preflight and close completed issues**

Run: `bd preflight`, then close `brewq-asn` and `brewq-isb` only if every acceptance criterion is demonstrated by the fresh verification output.

- [ ] **Step 5: Commit docs and tracker state**

```bash
git add AGENTS.md README.md docs/vision.md docs/product-spec.md docs/cli-design.md
git commit -m "docs: describe automatic cache lifecycle"
```

Commit any tracked beads interaction export separately with `chore(beads): close cache lifecycle work`.
