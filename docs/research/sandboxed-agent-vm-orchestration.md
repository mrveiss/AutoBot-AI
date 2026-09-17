# Sandboxed agent VM/container orchestration CLI — source analysis

Fetched 2026-09-17 via `gh api` (no clone). Source is anonymized per the research skill's
default: name and repo URL stay in the chat reply, not on disk.

## Source Analysis: a multi-provider sandbox-orchestration CLI for coding agents

### What It Is

A TypeScript/Node CLI (npm-published, pnpm + Turborepo monorepo, ~20 internal packages) that
spins up per-task sandboxes — a local Docker container by default, or one of several cloud
microVM backends — to run coding agents (three integrated: one Anthropic-style CLI agent, one
OpenAI-style CLI agent, one open-source agent; plus a pluggable "service" agent class) against
a *teleported* copy of the user's project. Maturity is pre-1.0 (every internal package is
version `0.0.0`), MIT-licensed, single publicly-credited maintainer, actively committed
(same-day activity at fetch time). Distribution is a global npm CLI plus an optional native
menu-bar tray app (separate sibling repo) and a small web "hub" app for cross-sandbox status.

### Architecture & Key Patterns

- **Provider plugin architecture.** A thin ~13-method backend interface (provision / get /
  start / stop / pause / resume / destroy / state / exec / upload / download / list-files /
  preview-url, with optional checkpoint/snapshot hooks) is wrapped by one factory function that
  supplies the *entire* generic sandbox lifecycle (workspace seeding, in-box supervisor launch,
  relay wiring, checkpoint plumbing) on top of it — the stated design goal is "a cloud backend
  is one file." All seven built-in backends (local Docker, remote Docker over SSH, and five
  cloud VM providers) implement this same interface; third-party backends ship as independent
  npm packages built against a public, versioned provider SDK that inlines the private core so
  external plugins never import internal packages, and are loaded at runtime via a recorded
  dynamic `import()` — no core-repo change needed to add a backend.
- **Declared, not inferred, capability manifest.** Providers separately declare a small
  descriptor object (checkpoints? ssh? inbound networking? pause semantics?) rather than the
  orchestrator probing "does this object have a `.checkpoint` method" — the docs call this out
  explicitly, because the shared factory gives *every* cloud provider default implementations of
  several optional methods, so method-presence alone is not evidence of support.
- **Two long-lived processes.** An in-container supervisor runs a declarative YAML-defined DAG
  of one-shot tasks and long-running services (dependency ordering, readiness probes, restart
  with backoff, a single reserved "web" port); a host-side relay process brokers git push/pull
  and checkpoint capture using the *host's* own credentials — sandboxes never hold git/SSH
  credentials themselves.
- **No filesystem overlay.** An earlier FUSE-overlay design was retired in favor of running
  `git worktree add` *inside* the container against the host's `.git/` directory (bind-mounted
  at an identical absolute path), so the agent gets a real git worktree/branch while the host's
  own checkout is never touched. A tar-pipe fallback handles non-git projects.
- **Pause, not stop, as the core efficiency mechanism.** Idle sandboxes are frozen via the
  container runtime's cgroup-freezer pause rather than stopped — zero CPU, memory stays mapped
  — giving near-instant resume with warm language-server/build caches, versus a stop/start cycle
  that would cold-start those caches.
- **Checkpoints via layered image commits.** A checkpoint is a container-engine image commit;
  chains beyond a configurable depth are automatically flattened (export the merged filesystem,
  rebuild a single-layer image) to bound image history growth. New sandboxes can start from a
  checkpoint instead of paying dependency-install cost from scratch.
- **One config source of truth.** A single registry object drives the parser, the JSON Schema,
  and CLI flag type-coercion together, specifically to prevent the three from drifting apart as
  config keys are added. Config itself is layered (global → per-project → per-workspace →
  CLI-flag override).
- **Credential propagation loop.** A poller inside the container watches each agent's own
  credential file for valid-shaped changes and reports them back over the relay, so logging in
  inside one fresh sandbox becomes the new shared default credential for future sandboxes.

### Notable Implementation Details

- Session continuity across sandbox restarts is solved by having each agent's own lifecycle
  hooks write a session identifier (or, for an agent with no resumable session id, a presence
  marker) to a sandbox-local path that is *not* part of the shared, cross-sandbox credential
  volume — because credentials/session state pool across every sandbox on the host, the
  supervisor otherwise has no way to know which session belongs to which sandbox.
- Agent "activity state" (working / idle / waiting-on-user / erroring) is derived from two
  independent signals: the agent's own lifecycle hooks (primary) and a periodic tmux
  pane-content scraper (secondary, promote-only) that only upgrades a stuck "working" state to
  "waiting" — never overriding a richer hook-driven state — because hook coverage for at least
  one of the three integrated agents is documented as unreliable in current releases.
- The global sandbox registry (one JSON file recording every live sandbox) is protected by a
  cross-process file lock around each read-modify-write cycle; the docs record this as a fix for
  a real incident where concurrent create/destroy silently corrupted the registry and made
  sandboxes vanish from listings.
- Every host-authoritative shared state sync (agent credentials, agent-specific config, a
  cross-agent "skills" directory) follows the same additive merge rule: host wins on any
  overlapping key, sandbox-only local additions survive, keeping a sandbox's own in-sandbox
  config changes (e.g., an agent extension installed only inside that sandbox) from being wiped
  on the next sync.

### Strengths

- Provider abstraction is unusually disciplined for the project's maturity stage: a genuinely
  thin backend interface, an explicit compatibility-version gate on the plugin SDK, and a
  written rule against inferring capabilities from method presence rather than an explicit
  manifest.
- The architecture doc includes an explicit "what we rejected and why" section (FUSE overlay,
  per-project checkpoint volumes, credential forwarding into the container) with the concrete
  operational failure each alternative produced — an unusually transparent design record for a
  public repo.
- Credential handling is a deliberate, consistently-applied constraint: the sandbox itself never
  receives git push or SSH credentials; every operation needing them is executed host-side and
  invoked through a local relay.

### Weaknesses / Limitations

- Single maintainer, pre-1.0 versioning across the board, and considerable per-OS/per-runtime
  fragility surface (nested container-in-container storage-driver fallbacks, cgroup/apparmor
  flags, FUSE availability) — both bus-factor and platform-brittleness risk look high.
- Cloud-provider parity is uneven despite the unifying interface: the README's own support
  matrix marks one built-in cloud backend "Partial" and checkpoint/snapshot support there
  "Experimental."
- Shared, host-authoritative config/credential merging across all three supported agents is
  admitted in the docs to be "best-effort" in places, with a real documented failure mode (a
  teleported session resuming at the wrong working directory) that had to be specifically
  patched around.
- The whole design is Node/TypeScript-and-Docker-specific; there is no path for non-Docker
  container runtimes or Kubernetes-style orchestration, which narrows applicability to teams
  already using Docker Desktop/OrbStack-class local tooling.

### Visible vs Hidden Metrics

- **Visible:** GitHub star count, npm download badge, "sub-1-second" checkpoint/pause-resume
  switching claims — all self-reported in the README; no independent benchmark located.
- **Hidden:** running the in-container supervisor requires a nested container engine inside
  every sandbox with elevated capabilities (`SYS_ADMIN`, unconfined AppArmor/seccomp) — a
  materially larger per-sandbox attack surface than a plain, unprivileged dev container; a
  genuinely large amount of ongoing reconciliation logic — one bespoke three-way
  config/credential merge implementation per supported coding agent, each independently
  versioned and each with its own documented edge cases; and a specific toolchain lock-in
  (pnpm workspaces + Turborepo + a custom bundler config + a hand-versioned plugin-SDK
  compatibility scheme) that an adopting team would need to either take on wholesale or
  reimplement piecemeal to reuse any single mechanism.
- **Weighing:** the pause/checkpoint speed claims are mechanistically credible — cgroup-freeze
  pause and layered image commits are well-understood primitives, not marketing dressing — but
  they are bought with meaningfully more privileged containers and an open-ended per-agent
  maintenance surface. That trade only clears for a team running many concurrent, disposable,
  fully-isolated agent sandboxes per developer; for a single-agent-at-a-time workflow the added
  privilege and maintenance burden likely outweigh the switching-speed win.

## AutoBot Comparison: the reference work → AutoBot

Scope: focused on sandboxing/isolation per operator request, since AutoBot's execution-backend
sandboxing is acknowledged as not fully implemented.

### What We Can Adopt

**1. A pause/resume primitive on the execution-backend interface**
- Applies to: `autobot-backend/services/execution/base_backend.py` (the `ExecutionBackend` ABC),
  `docker_backend.py`.
- Already-exists audit: `base_backend.py` (full file) defines `execute` / `health_check` /
  `cleanup` / `snapshot` / `restore` / `delete_snapshot` / `get_snapshots_for_session` — no
  `pause`/`resume`. `grep -n "def pause\|def resume\|pause\|resume"` across
  `services/execution/*.py` returns nothing container-related; the only `SIGSTOP`/`SIGCONT` hit
  in the repo (`api/terminal.py:622-623`) is PTY job control, unrelated to container lifecycle.
- Visible benefit: near-instant resume of an idle agent sandbox with warm caches (deps,
  language-server state) instead of a fresh `containers.run` or a full snapshot/restore
  round-trip — directly reusable for AutoBot's multi-worktree / multi-session agent switching.
- Hidden cost: `docker pause` freezes the whole container, including whatever the health probe
  (`api/sandbox_health.py`) pings — that probe would need a third state ("paused", not
  "unhealthy") or a paused container looks like a dead one; also widens reliance on Docker
  daemon liveness, the exact dependency `sandbox_health.py` was written to stop over-trusting.
- Verdict: **adopt-with-conditions** — add as two new methods on `ExecutionBackend` with the
  same default-`NotImplementedError` pattern already used for `snapshot`/`restore`, implement
  only for `DockerBackend` first, and teach `sandbox_health.py` the paused state before wiring
  any caller to it.
- Effort: moderate.

**2. A declared per-backend capability manifest, instead of re-deriving capability ad hoc**
- Applies to: `autobot-backend/services/execution/base_backend.py` (`BackendType` enum),
  `execution_manager.py` (routing/compatibility), `api/sandbox.py` (`/stats` capabilities
  block), `api/sandbox_health.py`.
- Already-exists audit: `base_backend.py`'s `BackendType` enum (`LOCAL`/`DOCKER`/`SSH`/`MODAL`,
  plus `ClaudeCodeBackend`) carries no capability data of its own; `execution_manager.py`
  decides per-task compatibility via `verify_task_compatibility()` and separately warns when a
  task silently downgrades off `DOCKER` (lines 106-116, #14872); `api/sandbox.py:325-341`
  derives `network_isolation`/`resource_limits` from the live health probe now, but only for the
  single ad hoc `secure_sandbox_executor` instance, not for the 5-backend `ExecutionBackend`
  family — each caller re-derives "is this actually isolated" independently rather than reading
  one static, backend-keyed manifest.
- Visible benefit: this is precisely the bug class AutoBot already shipped once — `/stats`
  hardcoded `"network_isolation": True` regardless of reality until #14872 caught it. A
  declared manifest (which `BackendType` values support snapshot/restore, pause/resume,
  network isolation, resource limits) read by every caller removes the class of bug, not just
  the one instance.
- Hidden cost: one more schema to keep honest against actual backend behavior; only pays for
  itself once backends genuinely diverge in capability, which AutoBot already has (5 backends,
  only Docker does real isolation + snapshot).
- Verdict: **adopt** — targets a bug class with a confirmed prior incident (#14872), not a
  hypothetical.
- Effort: moderate.

**3. Bounded snapshot chain depth (auto-flatten)**
- Applies to: `docker_backend.py` `snapshot()` (391-458) / `restore()` (460-510).
- Already-exists audit: `restore()` (460-510) starts a new container directly from the
  snapshot's committed image with no chain-depth bookkeeping; a repeated
  restore→modify→snapshot cycle on the same lineage keeps committing a new layer on top of the
  last snapshot image indefinitely — there is no flatten/export step anywhere in the file.
- Visible benefit: bounds image-layer growth and `docker commit` time for long-lived,
  repeatedly-restored agent sessions.
- Hidden cost: extra `docker export`/rebuild machinery and a threshold config value to add and
  maintain; only matters once a lineage is restored+re-snapshotted many times, which may not
  happen often in AutoBot's current usage.
- Verdict: **adopt-with-conditions** — cheap to defer until `SnapshotRecord`/`_snapshot_index`
  data shows real chains forming; not worth building speculatively.
- Effort: trivial to moderate (depends on whether chain lineage needs tracking first).

### What We Already Do Better

- **Git-worktree-based workspace isolation is already the same design, already shipped.**
  `autobot-backend/services/task_workspace.py` (504 lines) — `allocate()`/`release()`/
  `cleanup_stale()`, `git worktree add` per task (line 404), `.active-lock` guard against races
  (line 44, GH#11059), nightly Celery eviction (`tasks/workspace_cleanup.py`, GH#6471), and a
  dedicated test suite (`tasks/test_task_workspace.py`). The reference work arrived at the exact
  same conclusion (worktree-in-place beats a filesystem overlay) later in its own history, after
  explicitly rejecting a FUSE-overlay design — AutoBot never built the overlay in the first
  place. Company-OS LLC leases extend the same worktree pattern (`llc/models/workspace_lease.py`).
- **Credentials are centralized through a secrets manager, not propagated from inside a
  sandbox.** AutoBot's model (`autobot_shared` secrets manager, per project convention) never
  needs a poller watching an in-sandbox credential file for change-and-forward, because the
  sandbox was never the source of truth for the credential to begin with — a stronger guarantee
  than "the sandbox's own credential file changes get synced back," which still has to trust
  what the sandbox wrote.
- **Silent-downgrade is already surfaced, not just designed against.** `execution_manager.py`
  logs `"this execution is NOT sandboxed (#14872)"` the moment a task meant for `DOCKER` runs
  anywhere else, and `secure_sandbox_executor.py:966` logs `"...SECURITY RISK"` when the Docker
  SDK is absent. This is the same transparency instinct as the reference work's "what we
  rejected" doc section, applied at runtime instead of only in a design doc.

### Gaps & Opportunities

Ranked by how directly each maps to "sandboxing is not fully implemented":

1. **Snapshot/restore is implemented only for `DockerBackend`.** `base_backend.py:202-260`
   defines `snapshot`/`restore`/`delete_snapshot`/`get_snapshots_for_session` as
   `NotImplementedError` by default; `grep` across `local_backend.py`, `ssh_backend.py`,
   `modal_backend.py`, `claude_code_backend.py` finds zero overrides — every non-Docker backend
   silently cannot checkpoint. This is the single most literal match to "sandboxing... not fully
   implemented." Not all four need full support, but each should at minimum get a docstring/
   issue link stating why (e.g., Modal has its own native snapshot primitive worth wrapping
   instead — open issue #11086 already flags the Modal backend as unverified against its real
   SDK, a natural place to add this).
2. **No pause/resume state anywhere in the execution-backend stack** (see adopt item #1) —
   today the only lifecycle states are running/stopped via full `execute`/`cleanup`, with no
   middle "frozen, resumable" state.
3. **Docker SDK remained an undeclared dependency until #14872** — already fixed
   (`requirements.txt:148`), but it is the same fragility class the reference work's own
   `sandbox_health.py`-equivalent design targets: don't let a health/capability claim outrun
   what's actually installed and reachable. Worth a regression test asserting `docker` and
   `modal` stay declared, given it silently regressed once already.

### Specific Code/Files Affected

| File | Change |
|---|---|
| `autobot-backend/services/execution/base_backend.py` | Add `pause()`/`resume()` with the existing `NotImplementedError`-default pattern; add a `BackendCapabilities` descriptor keyed by `BackendType`. |
| `autobot-backend/services/execution/docker_backend.py` | Implement `pause()`/`resume()` via the Docker SDK's pause/unpause; optionally add chain-depth tracking to `snapshot()`/`restore()`. |
| `autobot-backend/services/execution/execution_manager.py` | Read the new capability descriptor instead of (or alongside) `verify_task_compatibility()` for routing decisions. |
| `autobot-backend/api/sandbox_health.py` | Add a `paused` containment state distinct from `unhealthy` once pause/resume lands. |
| `autobot-backend/services/execution/{local,ssh,modal,claude_code}_backend.py` | Each gets either a real `snapshot`/`restore` implementation or an explicit "why not" docstring/issue link, closing the silent-gap pattern `base_backend.py` currently allows. |
