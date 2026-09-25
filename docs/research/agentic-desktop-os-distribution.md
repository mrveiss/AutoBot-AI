---
tags:
  - research
  - agents
  - operations
aliases:
  - Agentic Desktop OS Distribution
---

# An Agent-Native Desktop OS Distribution

Phase 1 (source analysis) and Phase 2 (AutoBot comparison) complete. The source is a
single-vendor opinionated desktop distribution; it is described generically here per the research
anonymization rule.

## Source Analysis: an opinionated, agent-native desktop OS distribution

### What It Is

A vendor-curated desktop operating system distribution built on a rolling-release Linux base and
a Wayland compositor, whose stated position is "the malleable OS for the age of agents". It ships
an installer measured in seconds, a fixed set of opinionated defaults (editor, terminal, shell,
theming, dev stacks, gaming launchers, a Windows VM path), a first-class CLI that fronts every
internal operation, and — the part that distinguishes it from the many other opinionated desktop
spins — a built-in agent layer: ten agent CLIs (ours among them) as lazy-installing stubs, a
skill directory symlinked into each vendor's skill path, an unattended `agent prompt <task>` entry
point, a crash-diagnosis flow wired to the OS core-dump facility, and a panel that tracks each
agent subscription's session and weekly limit usage. Maturity: young but past its first major
releases, with substantial platform-verified popularity, a sizeable contributor base, and a
foundation holding significant pledged funding. Governance is explicit single-owner benevolent
dictatorship, stated as doctrine, not an accident of the project's age.

### Architecture & Key Patterns

- **One CLI as the single operational surface.** Every menu action, every system tweak and every
  update path is a `<tool> <group> <command>` invocation; the GUI menu is a front-end over the
  same commands. The CLI is introspectable (`commands --all --json`, per-group `--help`), and the
  docs name agent-driven customization as a first-class use.
- **The distro's own update path replaces the base package manager.** Direct `pacman`/AUR
  invocation is blocked; the wrapper couples three things into one atomic-ish operation — release
  install, **pending migrations**, and package upgrade — so config-format changes never lag
  packages. Four release channels (stable on a mirror deliberately one month behind, edge, RC, and
  a git checkout for contributors).
- **Snapshot-before-mutate at the boot-loader level.** Every update takes a root-filesystem
  snapshot, selectable from the boot menu by date and version; booting a snapshot prompts a
  restore. Restore covers root and explicitly **not** `/home`.
- **Two-tier plugin tree with namespaced IDs.** First-party plugins under the install path,
  third-party under `~/.config/<tool>/plugins/`, discovered by identical mechanism at shell
  startup; third-party IDs are `<username>.<plugin>` and the first-party prefix is reserved. A
  `manifest.json` declares `schemaVersion`, id/name/version, one or more *kinds*
  (bar-widget, panel, overlay, menu, service, bar) and an `entryPoints` map from kind to a
  declarative-UI file. Enablement is derived from presence in the shell config rather than stored
  as a separate flag, with a `disabledPlugins[]` opt-out for first-party defaults.
- **Agent CLIs as managed, lazily-installed stubs.** Version-manager-backed shims in
  `~/.local/bin/` install on first invocation; a default agent is a config setting; a generic
  `<tool>-mise-install <package> [name]` wraps any further CLI into the same shape. Theme changes
  propagate into the agent CLIs' own configs.
- **Skill as the integration contract.** One skill directory symlinked into five different
  vendors' skill paths — so a single skill body teaches every installed agent the same host
  vocabulary, instead of N per-vendor integrations.

### Notable Implementation Details

- **Crash → agent, automatically.** A core-dump watcher raises a "process crashed" notice whose
  action invokes a `diagnose-crash` skill against that PID; per-program muting is a first-class
  command (`crash mute <program|path>`). The triage entry point is the notification, not a log the
  user must find.
- **Agent run directory is coerced away from `$HOME`.** An unattended agent launched from the home
  directory is started in `~/Work` instead, with the stated reason that agents refuse to persist a
  trust decision for the home directory — a workaround for a *provider* safety rail, which is an
  honest signal of where the friction is.
- **Plugin update is a refusing fast-forward.** Updates are fast-forward git pulls that show the
  diff first, **refuse** when local modifications exist, and roll back on manifest-validation
  failure. Save-to-reload: writing any file under the third-party plugin dir hot-reloads it.
- **Subscription headroom as a panel.** Plan, 5-hour session percentage and weekly percentage per
  agent, refreshed on a 15-minute timer — usage limits treated as an operational metric with a
  display surface, not as an error you discover mid-task.
- **Enablement derived from use.** A bar widget placed in the layout *is* enabled; there is no
  second registry to drift out of sync with the layout.

### Strengths

- Update, migration and snapshot are one flow, and the escape hatch (boot a pre-update snapshot)
  needs no working userland.
- A machine-readable, fully-introspectable CLI covering 100% of operations is the cheapest possible
  agent surface — no bespoke tool schema, no API to keep in sync with the UI.
- The skill-symlink pattern makes host integration O(1) in the number of agent vendors.
- Failure paths are named and have commands (`reinstall`, `reinstall configs`, `snapshot restore`,
  crash mute), rather than being left to forum threads.
- Its own docs label the agent-integration skill **experimental** and tell the reader to be ready to
  roll back — calibrated rather than promotional.

### Weaknesses / Limitations

- **The agent trust boundary is undocumented.** Unattended agent runs are stated to use
  "auto-approving modes" that "actually do things", on a user account that is `sudo`-capable (and
  optionally passwordless for 15 minutes). The security page covers disk encryption, firewall,
  SSH and release signing, and is **silent on agents and on plugins** — the two things the product
  is differentiated by.
- **Plugins are unsandboxed code in a long-lived process,** explicitly: arbitrary code with full
  user-account access inside the shell process, mitigated only by "confirm before adding" and
  "review the code yourself". The community registry exposes a verified/unverified filter with no
  published verification criteria.
- **Snapshot rollback is half a rollback.** Root reverts, `/home` does not — so a
  rolled-back application meets its own newer config format, and the docs hand that conflict to
  the user. `reinstall` resets config by overwriting user modifications wholesale; there is no
  described three-way merge between vendor defaults and user edits.
- **No plugin dependency system,** stated outright — ordering and prerequisites are the author's
  problem.
- **Rollback depends on one boot loader** (default only since the 2.x line); the "direct boot"
  speed option removes access to the snapshot menu entirely.
- Single-owner governance is doctrine; bus factor and roadmap are one person's, by design.

### Visible vs Hidden Metrics

- **Visible:** a large self-reported first-year download count and a substantial figure for the
  latest release; a sub-two-minute install (self-reported); a landing-page claim of a large
  community plugin catalogue, while the registry page itself rendered **0 indexed plugins** at
  fetch time (unverified, and internally inconsistent); a wide theme and locale selection; runs on
  decade-old hardware with 2GB RAM (self-reported demo); significant pledged foundation funding.
- **Hidden:** (1) you inherit a rolling-release base's churn, deliberately lagged one month —
  the lag is the mitigation *and* the delay on security fixes; (2) replacing the base package
  manager means the vendor now owns an update path that must stay correct forever, and a user who
  needs the native tool is off the supported path; (3) unsandboxed plugin code in a long-lived
  shell process is a user-account compromise per installed plugin, and the registry's
  verification is unexplained; (4) auto-approving agents on a sudo-capable account is an
  unbounded blast radius with no documented containment; (5) rollback asymmetry (root yes, `/home`
  no) means config conflicts are manual work exactly when the system is already broken;
  (6) bus factor 1 by doctrine; (7) a many-sectioned manual is the real learning curve behind the
  "fantastic defaults" claim.
- **Weighing:** the visible wins are adoption and install speed, which are the *distribution's*
  metrics and transfer to nobody else. What transfers is the mechanism set — one introspectable
  CLI as the whole operational surface, migrations coupled to package updates, snapshot-before-
  mutate with a userland-independent escape hatch, crash-notice-to-agent triage, one skill body
  symlinked per vendor, and subscription headroom as a displayed metric. Each of those is cheap
  and low-coupling in isolation. The hidden costs cluster almost entirely in the *agent and plugin
  trust model* — unsandboxed plugin code, auto-approving agents on a root-capable account, and a
  security document that does not mention either — so any adoption that copies the convenience
  patterns without a containment story inherits the one part of this source that is
  demonstrably weakest, and that part is precisely where AutoBot already has explicit doctrine.

---

## AutoBot Comparison: the reference work → AutoBot

Method: four parallel read-only audits (update/migration/snapshot path; plugin trust boundary;
agent approval surface; CLI + usage headroom + crash triage), then the decisive claims
re-verified by hand. Every claim below cites `file:line`. Where something was not found, the
greps that came back empty are named — *nothing found* and *did not look* are kept apart.

### What We Can Adopt

#### 1. Snapshot-before-mutate + auto-rollback on the **primary** update path — ADOPT

- **Already-exists audit:** AutoBot has both halves of this pattern, on the *wrong* path, and the
  snapshot half is **best-effort rather than guaranteed**: `_snapshot_component()` returns
  `Optional[str]` with three `return None` paths, and its caller (`code_sync.py:3032`) passes the
  result into every component branch **without checking it**, so a failed snapshot still lets the
  post-sync mutations run and leaves `_rollback_component()` with nothing to restore (filed as
  #17474). The drift-resolve path attempts to snapshot before touching anything —
  `autobot-slm-backend/api/code_sync.py:3032` calls `_snapshot_component()`
  (`code_sync.py:2467-2511`) with the comment "snapshot the deployed dir BEFORE any mutation for
  rollback", and `_rollback_component()` (`code_sync.py:2555-2585`) has seven call sites
  (`:2890, :2901, :2913, :2926, :2938, :2950, :2968`) restoring via
  `_restore_component_snapshot()` (`:2514-2552`). DB safety is fail-closed on both paths
  (`_pg_dump_before_migration()` `code_sync.py:2114-2187`, called `:2226`, aborts the migration on
  `None` at `:2227-2230`; and `ansible/_shared/tasks/pre_migration_backup.yml` invoked from
  `migrate_backend_db.yml:29-30`).
- **Missing delta:** the *actual* self-update / update-all path has **no filesystem snapshot
  before `unarchive` and no rollback task after a failed health check**. The health polls exist
  (`ansible/playbooks/update-all-nodes.yml:679-689` and `:1311-1325`) and nothing follows them but
  a failed play. A bad deploy leaves `/opt/autobot/` half-written with the previous archive gone.
- **Visible benefit:** a failed update reverts itself instead of needing a human at a console.
- **Hidden cost:** rsync snapshots of the deployed tree cost disk per node and add a step to the
  slowest part of the flow; retention needs an owner or it grows unbounded.
- **Verdict:** adopt — this is porting a mechanism AutoBot already wrote and tested, not importing
  a foreign one. **Effort: moderate.**

#### 2. Wire the already-built quota headroom to a display surface — ADOPT

- **Already-exists audit:** fully built and unreachable. `autobot-backend/llm_shared/quota_headroom.py:94-113`
  defines `QuotaHeadroomEntry` with a computed `.utilization` (`:107-112`), persisted to Redis
  (`:85, :128-252`, TTL `AUTOBOT_LLM_QUOTA_HEADROOM_TTL_SECONDS`, default 3600s at `:83`), fed from
  real provider rate-limit headers and 429s via `llm_shared/rate_limit_backoff.py`. The window
  vocabulary already matches session/weekly shape — `autobot-backend/llc/api/costs.py:74-93` maps
  Anthropic to `["5h_output_tokens", "7d_output_tokens"]`. `GET /api/llc/costs/quota-windows`
  (`costs.py:299-330`) serves it, docstring at `:305-310` insisting it is the provider's own
  numbers, "never a computed guess".
- **Missing delta:** no frontend consumer. `grep -rn "quota-windows|quotaWindows" autobot-frontend/src
  --include=*.ts --include=*.vue` (generated client excluded) returns **zero** hits; the cost views
  render lifetime totals from `/costs/by-agent-model` and `/costs/step-rollup`
  (`autobot-frontend/src/composables/llc/orgNodeSidebar.ts:174-179`,
  `autobot-frontend/src/views/llc/CostDashboard.vue:591`), not headroom.
- **Visible benefit:** limit exhaustion becomes a number you watch instead of an error you discover
  mid-run.
- **Hidden cost:** one more polling surface; a stale reading is worse than none, so the display must
  show `observed_at`.
- **Verdict:** adopt — the cheapest item in this document, and it is the "wire it in, never delete"
  rule applied literally. **Effort: trivial.**

#### 3. Failure → automated diagnosis, with a per-source mute — ADOPT-WITH-CONDITIONS

- **Already-exists audit:** the engine exists, the trigger does not. The unhandled-exception
  handler `autobot-backend/app_factory.py:64-70` logs and returns a generic 500 — it starts
  nothing. `POST /diagnostics/analyze-failure` (`autobot-backend/api/diagnostics.py:52-79`) demands
  an explicit `task_id` (`:66-67`), so a human must already know what broke.
  `CausalInferenceEngine.analyze_failure` (`autobot-backend/services/causal_inference_engine.py:148-185`)
  is statistical, not LLM-based, and its one in-process construction site
  (`autobot-backend/services/grounded_agent.py:97-98`) is never followed by a call —
  `grep -n "self.causal_engine\." grounded_agent.py` is empty. `self_heal|auto_diagnos|diagnose_crash|
  post_mortem|crash_report` repo-wide: only test files for the mechanical reconciler.
- **Missing delta:** an automatic trigger from a captured failure into the diagnosis path, plus the
  source's `crash mute <program>` equivalent.
- **Visible benefit:** triage begins at the notification, not when someone finds the log.
- **Hidden cost:** this is the item whose hidden cost is largest — auto-diagnosis on every 500 is a
  token-spend amplifier and a self-inflicted log-spam loop. The source ships per-program muting for
  exactly this reason; adopting the trigger without the mute and a dedupe key is a cost bug.
- **Verdict:** adopt-with-conditions — trigger only on distinct, deduped failure signatures, rate-
  limited, with a mute list, and diagnosis stays advisory: remediation keeps the human gate that
  `autobot-slm-backend/services/reconciler.py:6-11` already draws. **Effort: moderate.**

#### 4. Detect out-of-band deployment mutation (the "blocked package manager", adapted) — ADOPT-WITH-CONDITIONS

- **Already-exists audit:** the rule is doctrine, unenforced. `CLAUDE.md` mandates that system
  updates go through the builtin updater only; **no guard enforces it** — NOT FOUND after checking
  for apt-mark hold / dpkg selections lockdown / `chattr +i` on deployed dirs / polkit or sudoers
  restrictions across `autobot-slm-backend/ansible` (only ordinary `unattended-upgrades` config at
  `ansible/playbooks/deploy-base.yml:231-238` and a package *rollback* helper at
  `ansible/roles/dependency_patching/tasks/rollback-system.yml:138`). `git` is in `SAFE_COMMANDS`
  (`autobot-backend/security/command_patterns.py:273`) — unrestricted even for the agent. What does
  exist is concurrency-only: `_reject_if_deploy_in_progress` (`code_sync.py:1734`) and the 409 in
  `_start_update_all_locked` (`code_sync.py:5895-5929`) stop overlapping *builtin* runs, not manual ones.
- **Missing delta:** a drift check that reports a deployed tree mutated outside the updater.
- **Visible benefit:** the doctrine becomes measurable instead of aspirational.
- **Hidden cost:** a hard *block* would lock an operator out of recovery exactly when recovery is
  needed — the source's approach, and the wrong half to copy.
- **Verdict:** adopt-with-conditions — **detect and report, never block**; the escape hatch stays
  open. **Effort: moderate.**

#### 5. One introspectable operator surface — REJECTED AS SHAPED, defect kept

- **Already-exists audit:** AutoBot has no canonical CLI —
  `grep -rln "^import click|^import typer|from click|from typer"` repo-wide is **zero hits**; root
  `pyproject.toml` has no `[project.scripts]`. Five non-delegating entry points exist: `./autobot:59-131`
  (bash `case`), `scripts/autobot-ctl:50-99` (a second lifecycle CLI, driving `systemctl`, unaware of
  the first), `autobot-backend/cli/doctor.py:252-259`, `autobot-backend/cli/agent_wiki.py:8-13`,
  `autobot-slm-backend/scripts/autobot-admin.py:6-19`; `main.py:1-30` is a deprecated stub. No `--json`
  introspection in any of them. `scripts/` holds 114 files (`find scripts -type f -not -path "*__pycache__*" | wc -l`).
- **Why rejected as shaped:** the source needs a CLI because it has no API. AutoBot is API-first and
  already ships machine-readable introspection of every operation — the OpenAPI schema behind
  `autobot-frontend/src/types/generated/api.ts`. Adding a CLI layer would be a second front door
  free to drift from the first, which is the coupling cost the hidden-metrics column exists to catch.
- **What survives:** the *single-dispatcher* discipline, as a defect rather than an adoption — three
  unrelated paths to one "start/stop/status" concept (`./autobot:65-69` docker-compose + `pkill`;
  `scripts/autobot-ctl:50-99` systemctl; GUI → REST), and `./autobot` `setup`/`repair` exec
  `setup_agent.sh` / `setup_repair.sh`, **neither of which exists in the repo** — two of seven
  documented subcommands are dead references.

#### 6. One skill body shared across agent backends — NOT AUDITED

The source symlinks a single skill directory into five vendors' skill paths, making host integration
O(1) in agent vendors. AutoBot's analogue would be one instruction/skill body shared across the
execution backends (`autobot-backend/services/execution/`). **This pass did not audit it**, so it is
recorded as unassessed rather than as a gap — it needs its own audit before any verdict.

### What We Already Do Better

| Dimension | AutoBot | The reference work |
|---|---|---|
| Who may approve | `require_interactive_human()` (`autobot-backend/api/user_management/human_decider.py:26-37`) guards approve/reject/revision (`api/approval_gates.py:233, :267, :301`; `llc/api/approvals.py:138`), backed by `autobot_shared/auth/interactive_principal.py:95-110` which denies service keys, run/device JWTs and auth-disabled stand-ins — deny-by-default by construction (`:19-21`) | Unattended agents run in "auto-approving modes" on a `sudo`-capable account; the security page mentions neither agents nor plugins |
| Auto-approve blast radius | Bounded: a rule must be seeded by a prior human approval (`services/agent_terminal/service.py:442-447`) and the role's risk ceiling is checked *first* (`command_approval_manager.py:198-244` via `service.py:654`, before the auto-approval step at `:744`) | Documented as "actually do things", no containment described |
| The provider bypass flag | Actively stripped: `--dangerously-skip-permissions` cannot be passed (`services/execution/claude_code_backend.py:447`; `sanitize_tool_names()` proven by `autobot_shared/cli_tool_flags_test.py:20`) | The equivalent friction is *worked around* — an agent started from `$HOME` is silently redirected to `~/Work` because agents refuse to persist home-directory trust |
| Command risk | Tiered `CommandRisk` (`autobot_shared/status_enums.py:210-240`) with anti-evasion normalization — NFKC, homoglyph and C0-control stripping (`security/command_patterns.py:403-431`) — enforced pre-execution at four call sites | No equivalent; the shell is the shell |
| Authority propagation | Monotonically-narrowing lattice (`autobot-backend/security/authority.py:38-80`): restrictions union, grants intersect, so relaying can never widen authority (`:22-28`); child delegation authority derived at `chat_workflow/delegation.py:138,184`; out-of-process engines fail closed rather than hold (`chat_workflow/run_authority.py:55-61`) | Not applicable — no authority model |
| Approval record | Durable Postgres rows (`models/approval.py:58-159`) committed transactionally (`services/approval_gate_service.py:337-377`), with `author_type` classified **server-side**, never client-supplied (`api/approval_gates.py:369-374`) | No approval concept |
| Plugin install hardening | Admin-gated (`plugin_manager.py:164,186`), zip-slip and symlink rejection, entry-count / ratio / size caps (`archive_safety.py:17-20,38-82`), `git clone` without a shell and with `protocol.file.allow=never` (`plugin_install.py:203-225`), per-name install lock and atomic `mkdir` claim (`:43-55,107-120`), config validated against the manifest's JSON Schema at load and update (`autobot_shared/plugin_sdk/loader.py:42-100,360-363`) | Plugin install is "clone the files, validate the manifest"; trust is "review the code yourself" |
| Migration discipline | Fail-closed in both directions: `pre_migration_backup.yml` aborts without a backup target, and SLM startup migrations abort the process on failure (`autobot-slm-backend/main.py:153-172`, raised at `:164-165,170-172`, hooked at `:225`) | Migrations run inside the update; failure recovery is "boot the snapshot" |
| Data rollback | `pg_dump` before every migration on both update paths | Root filesystem reverts; `/home` does not, so config conflicts land on the user by design |

The pattern: on *containment* AutoBot is not merely ahead, it is in a different category — the
source's one-line security posture for its differentiating feature is that you are the sandbox.

### Gaps & Opportunities

The audit's real output. Eight defects in AutoBot's own code, impact-ordered:

| # | Defect | Evidence | Impact |
|---|---|---|---|
| 1 | `POST /plugins/{name}/load` raises `TypeError` on **every** call — it passes `grant_capabilities=` to a signature that has no such parameter | call `autobot-backend/plugin_manager.py:271`; the only `PluginLoader.load_plugin` definition is `autobot_shared/plugin_sdk/loader.py:320` (`(self, manifest, config=None)`); `grep -rn "def load_plugin"` repo-wide returns just that plus the route function itself | The documented plugin-load endpoint is dead on arrival |
| 2 | Plugin capabilities are decorative: `CapabilityChecker.check()` (`autobot_shared/plugin_sdk/capabilities.py:164-198`) has **zero call sites** — `grep` over `autobot_shared/plugin_sdk/`, `plugin_manager.py`, `plugin_install.py`, `plugins/` finds none — and it is the only writer to the `plugin:capability:audit` stream (`:200-228`) | Grants live in an in-process dict (`capabilities.py:131`), never persisted; none of the 7 shipped core manifests reference a capability in their code | Declared-but-unenforced permissions, and `GET /plugins/audit` (`plugin_manager.py:639-687`) is structurally guaranteed empty — a guard that cannot distinguish *clean* from *never ran* |
| 3 | `trust_tier` is **self-declared inside the untrusted manifest** (`autobot_shared/plugin_sdk/base.py:138-141`) and drives auto-grant: `auto_grant = manifest.trust_tier == TrustTier.OFFICIAL` (`plugin_manager.py:269`). A plugin installed via zip/git always lands in `community-plugins/` (`plugin_install.py:66-69`) yet may write `"trust_tier": "official"` | Verified by reading both sites | Privilege self-escalation by string — masked today only by defect #1 crashing first |
| 4 | Plugin enable/disable state is **not persisted** (in-memory `BasePlugin.status`, `base.py:200-218`, in a process-singleton registry `base.py:245-262`) and startup enables *everything* discovered (`autobot_shared/plugin_sdk/plugin_manager.py:120-124`) | Only plugin *config* is persisted, to Redis (`plugin_manager.py:690-702`) | A deliberately disabled plugin silently re-enables on restart |
| 5 | The primary self-update path has no pre-mutation filesystem snapshot and no rollback after a failed health check | `ansible/playbooks/update-all-nodes.yml:679-689, :1311-1325`; the mechanism exists on the other path (`code_sync.py:3032, 2555-2585`) | A failed deploy is not self-reverting on the path operators actually use |
| 6 | Two audit stores describe themselves as tamper-resistant with no integrity mechanism: `services/audit_logger.py:9` claims it, and `grep -n "hash|hmac|chain|signature|integrity|checksum"` over that module returns nothing; `services/audit/audit.py`'s `AuditEvent` (`:63-80`) likewise has no hash or signature field, and entries are TTL'd | Read both modules | A documented security property that no code provides |
| 7 | Release channels are documented but unimplemented: `docs/developer/AUTOBOT_REFERENCE.md:186-190` specifies stable / beta / dev; `release_channel` / `update_channel` / tag-pattern handling is NOT FOUND across `autobot-slm-backend`, `autobot-backend/api`, `autobot_shared` and both frontends. What exists is a branch pin (`models/database.py:1017`, `allowed_branches: [main, release]` in the playbook) | Greps named above | Doc/code divergence on the update surface |
| 8 | `CommandApprovalManager.needs_approval()` (`command_approval_manager.py:246-301`) and its wrapper `approval_handler.needs_approval` (`services/agent_terminal/approval_handler.py:111-129`) have no production callers; the agent-loop `minimal` guard profile that disables approval entirely (`agent_loop/guard_profile.py:44-64`, branch at `agent_loop/loop.py:1636-1643`) sits in a module self-documented as not wired (`agent_loop/__init__.py:11-15`) | Greps over `autobot-backend/services/agent_terminal/` and repo-wide `AgentLoop(` | Dead approval helpers next to a live approval path — the risk is a future caller reaching for the dormant one. Wire or converge, do not delete |

Two secondary items, lower impact: plugin IDs have **no namespace reservation** — a core/community
name collision is resolved only by the incidental ordering of `plugin_dirs`
(`plugin_manager.py:57-63`, first-wins in `loader.py:277-302`); and plugin artifacts have **no
signature or checksum verification** (`grep -i "sign|checksum|sha256|cosign|gpg"` over
`plugin_install.py`, `archive_safety.py`, `plugin_manager.py`: no real hits) while the repo already
runs `cosign` for container images (`.github/workflows/image-sign.yml:117`) — the verification
habit exists one layer up and was never brought to plugins.

### Specific Code/Files Affected

| Change | Files |
|---|---|
| Snapshot + rollback on the primary update path | `autobot-slm-backend/ansible/playbooks/update-all-nodes.yml` (snapshot before `unarchive`, revert task after the health poll), reusing the shape of `autobot-slm-backend/api/code_sync.py:2467-2585` |
| Render quota headroom | new panel consuming `GET /api/llc/costs/quota-windows`; `autobot-frontend/src/views/llc/CostDashboard.vue`, a new composable beside `autobot-frontend/src/composables/llc/orgNodeSidebar.ts` |
| Fix the plugin-load TypeError and the trust-tier hole | `autobot-backend/plugin_manager.py:269-271`, `autobot_shared/plugin_sdk/loader.py:320` — trust tier must derive from install provenance (which directory the manifest was found in), never from the manifest |
| Enforce plugin capabilities | call `CapabilityChecker.check()` from the hook-dispatch path (`autobot_shared/plugin_sdk/hooks.py:248-292`) and the load path; persist grants beside plugin config (`plugin_manager.py:690-702`) |
| Persist plugin enablement | `autobot_shared/plugin_sdk/base.py:200-218`, `autobot_shared/plugin_sdk/plugin_manager.py:120-124`, persisted next to `plugin:config:{name}` |
| Failure → diagnosis trigger, deduped and mutable | `autobot-backend/app_factory.py:64-70` (emit a signature, not a call), `autobot-backend/api/diagnostics.py`, `autobot-backend/services/grounded_agent.py:97-98` (the existing dead wiring point) |
| Out-of-band mutation detection | `autobot-slm-backend/api/code_sync.py` drift surface |
| Audit-integrity claim | `autobot-backend/services/audit_logger.py:9` and `autobot-backend/services/audit/audit.py:63-80` — implement hash chaining or drop the claim |
| Converge the lifecycle entry points; remove the two dead subcommands | `./autobot:59-131`, `scripts/autobot-ctl:50-99` |

### Filed — cross-reference against the existing backlog

Every finding was searched against open **and** closed issues before filing
(`gh issue list --search "<terms>" --state all`). Six of fourteen were already filed; those got a
witness comment rather than a duplicate, per *one defect, one fix*.

| Finding | Status | Issue |
|---|---|---|
| Plugin capabilities never checked; `/plugins/audit` structurally empty | **filed** → #17217 | [#17459](https://github.com/mrveiss/AutoBot-AI/issues/17459) |
| No plugin namespace reservation — core/community shadowing by `plugin_dirs` order | **filed** → #17217 | [#17460](https://github.com/mrveiss/AutoBot-AI/issues/17460) |
| Release channels documented, unimplemented | **filed** → #10016 | [#17461](https://github.com/mrveiss/AutoBot-AI/issues/17461) |
| `./autobot setup`/`repair` exec missing scripts; three lifecycle paths | **filed** → #10016 | [#17462](https://github.com/mrveiss/AutoBot-AI/issues/17462) |
| Three approval policies, one enforced (dead `needs_approval`, `minimal` profile) | **filed** → #13413 | [#17463](https://github.com/mrveiss/AutoBot-AI/issues/17463) |
| No deduped failure→diagnosis trigger; causal engine has no caller | **filed** (standalone) | [#17464](https://github.com/mrveiss/AutoBot-AI/issues/17464) |
| Out-of-band deployment mutation undetectable | **filed** → #10016 | [#17465](https://github.com/mrveiss/AutoBot-AI/issues/17465) |
| `POST /plugins/{name}/load` TypeError | already filed — witnessed, **plus a correction** to its claim that capability enforcement works | #17420 |
| `trust_tier` self-declared; no artefact verification | already filed — witnessed | #17280 |
| Every plugin enabled at boot; enablement unpersisted | already filed — witnessed | #17421 |
| No snapshot/rollback on the primary update path | already filed — witnessed | #17262 |
| Audit writers claim tamper-resistance without hashing | already filed — witnessed | #17219 |
| Quota headroom has no display surface | already filed — witnessed with the zero-consumer grep | #15030 (umbrella #15021) |
| One skill body shared across agent backends | **not audited** — no verdict, needs its own pass | — |

Batching note recorded on the issues themselves: #17420, #17421, #17280, #17459 and #17460 all touch
`autobot_shared/plugin_sdk/` and `autobot-backend/plugin_manager.py` → **one agent, one PR** per the
same-file rule. #17262 and #17465 share the update path and likely batch together.
