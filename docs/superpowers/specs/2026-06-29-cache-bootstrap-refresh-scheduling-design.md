# Cache Bootstrap and Refresh Scheduling Design

Date: 2026-06-29
Tracker: `brewq-asn`, with `brewq-isb` as an implementation prerequisite

## Goal

`brewq` should answer the first query promptly without requiring users to learn
or run a cache command. Later queries should remain fast while stale data repairs
itself in the background.

The first-release behavior is:

- no user cache: render from a bundled seed cache, overlay local installed state,
  and schedule a background refresh
- fresh user cache: render immediately without scheduling work
- stale user cache: render immediately and schedule one background refresh
- unavailable or failed refresh: retain usable cached data and report the outcome
  without a traceback

`brewq refresh` remains an optional manual escape hatch. It is never required for
normal installation or use.

## Non-Goals

- no permanent daemon
- no polling while `brewq` is unused
- no install-time network request
- no launchd- or systemd-specific implementation in the first release
- no new public scheduler command or configuration surface
- no Windows support; Homebrew's supported macOS and Linux environments are the
  first-release platform boundary

## User-Visible State Model

| Cache state | Query behavior | Disclosure |
| --- | --- | --- |
| Bundled seed only | Render seed plus local installed overlay | `cache: bundled seed; refresh scheduled` |
| Fresh user cache | Render user cache | Existing concise age disclosure |
| Stale user cache | Render stale user cache | `cache: stale; refresh scheduled` |
| Refresh already scheduled or running | Render available data | Report the existing background state without spawning another worker |
| Last refresh partially succeeded | Render the newly written metadata cache | State that analytics are incomplete and a retry will occur later |
| Refresh failed, cache available | Render available data | State the failure concisely and retain the retry cooldown |
| No valid seed or user cache | Attempt a metadata-only foreground bootstrap with visible progress and a 60-second Homebrew timeout | Return an actionable installation/cache error if bootstrap fails, then schedule analytics after successful metadata recovery |

All disclosures go to stderr, including during TSV output.

## Bundled Seed Cache

Release CI generates a deterministic gzip-compressed cache from the same
Homebrew metadata and analytics sources used by `brewq refresh`. It is packaged
as application data and loaded through `importlib.resources`.

The seed contains:

- formula and cask metadata
- 30-day, 90-day, and 365-day analytics
- cache schema version
- generation timestamp
- no machine-specific installed state or binaries

The current 34 MB cache compresses to approximately 4.25 MB with gzip. This
package-size increase is acceptable in exchange for eliminating an empty-cache
first run.

The release build fails if the seed is missing, malformed, uses the wrong schema,
or lacks formulae, casks, or analytics. Gzip output uses a fixed timestamp so the
artifact is reproducible.

The loader prefers a valid user cache. It falls back to the bundled seed without
copying or mutating the packaged resource. A successful background refresh writes
the normal user cache atomically, after which the seed is no longer used.

## Local Installed-State Overlay

When and only when the bundled seed is selected, `brewq` builds a lightweight
local inventory before rendering.

It resolves the Homebrew storage roots with:

- `brew --cellar`
- `brew --caskroom`

Both commands complete in roughly 0.01 seconds on the current development
machine. `brewq` then reads local filesystem metadata; it does not make a network
request or call the measured 6.9-second `brew info --json=v2 --installed` path.

Formula inventory:

- enumerate formula directories under the Cellar
- read `INSTALL_RECEIPT.json` for installed versions
- use `source.tap` plus the formula directory name to reconstruct canonical names
- treat `homebrew/core` names as unqualified
- if several kegs exist, select the receipt with the newest installation time for
  the displayed installed version

Cask inventory:

- enumerate token directories under the Caskroom
- mark the token installed
- ignore dot-prefixed metadata directories, then select the remaining version
  directory with the newest modification time for the displayed installed version

The overlay updates only `installed`, installed `version`, and locally discoverable
formula binaries. Global metadata and analytics continue to come from the seed.
Unreadable or ambiguous local entries are skipped individually; they do not make
the first query fail.

## Background Scheduler

Scheduling is opportunistic and after-use. A normal search or list command first
renders its result, then performs the cheap scheduling decision before exiting.

The scheduler starts work only when:

- the bundled seed was used, or
- the user cache exceeds `cache.max_age_seconds`

It does not start work when a fresh user cache exists.

The first implementation uses a detached Python worker on both macOS and Linux:

- invoke an internal module through the current Python executable
- detach it with a new session and closed standard streams
- acquire the existing refresh lock before doing refresh work
- hold a separate scheduler lock while delayed work is pending, preventing
  duplicate sleeping workers
- run at a positive nice value where the platform permits it

The worker waits five minutes, then checks normalized one-minute load average
against CPU count. If normalized load is above `0.75`, it waits another five
minutes. It tries for at most 30 minutes, then records a deferred outcome and
exits. A later command may schedule another attempt after the retry cooldown.

This process is intentionally disposable. If logout, reboot, or process cleanup
kills it, the expiring state and locks allow the next command to schedule another
worker. Native launchd and systemd adapters remain future reliability upgrades,
not requirements for the cross-platform first release.

## Scheduler State

`refresh-state.json` lives beside the user cache and is written atomically. It
contains:

- state: `scheduled`, `running`, `complete`, `partial`, `deferred`, or `failed`
- scheduling, start, and completion timestamps where applicable
- last refresh outcome
- a single-line failure detail, truncated to 300 characters, with no traceback
- worker PID while scheduled or running

The parent process combines this state with lock acquisition. A stale
`scheduled` or `running` record does not permanently block recovery.

After `partial`, `deferred`, or `failed`, automatic attempts use a one-hour
cooldown. Explicit `brewq refresh` bypasses the scheduler cooldown but still
respects the refresh lock.

## Truthful Refresh Outcomes

`cache.refresh()` returns a typed result rather than `None`. Required outcomes:

- `fresh`: no write because the cache is within its freshness window
- `locked`: no write because another refresh owns the lock
- `complete`: metadata and analytics were written atomically
- `metadata_only`: metadata was written, but analytics retrieval failed

Unexpected failures remain exceptions at the cache boundary and are converted to
stable CLI or worker state at the caller boundary. The result includes the cache
path and optional analytics error detail.

Analytics retrieval must stop collapsing transport, parse, and incomplete-feed
failures into empty dictionaries. Each of the six feeds returns either parsed
data or a typed failure. A refresh is `complete` only when all six feeds succeed;
one or more failed feeds produces `metadata_only` rather than writing misleading
zero or unknown analytics as a complete result.

The scheduler depends on these outcomes:

- `complete` records success and clears retry pressure
- `metadata_only` records partial success and retains a retry cooldown
- `locked` reports that another refresh owns the work without claiming success
- `fresh` is a successful no-op only for manual or racing refresh requests

This satisfies `brewq-isb` as part of the scheduling implementation instead of
treating it as a separate user-facing project.

## Failure Handling

- Seed load failure falls back to a valid user cache when available.
- A release installation without either valid cache is exceptional. Foreground
  recovery runs only `brew info --json=v2 --eval-all`, reports progress on stderr,
  and terminates it after 60 seconds. It writes a metadata-only user cache and
  schedules analytics in the background. If metadata recovery fails, the command
  names the broken installation/cache state and exits without suggesting an
  explicit refresh prerequisite.
- Local inventory failures degrade individual installed markers, not global
  search.
- Background worker errors never corrupt or delete the last valid cache.
- Atomic cache and state writes prevent readers from observing partial JSON.
- Analytics failure may produce a metadata-only cache, but it is never described
  as a complete refresh.

## Packaging and Cross-Platform Boundary

The seed is package data, so Python wheels and Homebrew installations use the
same runtime behavior. Installation does not execute `brewq`, contact Homebrew,
or write to a user's cache directory.

The detached worker, `fcntl` locks, `os.getloadavg`, filesystem inventory, and
Homebrew path commands are common to supported macOS and Linux environments.
Platform-specific service managers can be added behind the scheduler boundary if
real reliability evidence justifies them.

## Verification

Implementation follows test-driven development and must cover:

- seed generation is deterministic and rejects incomplete source data
- built wheel contains a valid seed
- seed loader falls back only when the user cache is absent or invalid
- local formula and cask fixtures overlay installed names and versions correctly
- third-party tap names reconstruct correctly from receipts
- unreadable local inventory entries degrade safely
- first query with only a seed performs no network call
- fresh cache schedules nothing
- stale and seed-backed queries schedule exactly one detached worker
- repeated commands do not create duplicate workers
- load gating, maximum deferral, stale state recovery, and retry cooldown use a
  controllable clock rather than real sleeps
- refresh outcomes distinguish fresh, locked, complete, and metadata-only states
- metadata-only and failed refreshes remain visible and preserve usable cache
- TSV rows remain clean while cache state stays on stderr
- functional subprocess tests exercise seed-only first search and first `list`
  on macOS and Linux CI

Performance acceptance on the current development machine:

- seed load plus installed overlay should complete within two seconds
- scheduler decision on a fresh-cache command should add no subprocess
- stale-cache command should render before the detached worker performs refresh

## Documentation Changes

After implementation, update the product and CLI docs to remove explicit refresh
as a normal prerequisite. Document the four automatic states: bundled bootstrap,
fresh cache, stale-while-refresh, and background refresh failure. Keep manual
`brewq refresh` documentation limited to forced recovery and diagnostics.
