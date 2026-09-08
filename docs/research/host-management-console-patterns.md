# Host-management console patterns — source analysis

Research artifact. Phase 1 is source analysis; Phase 2 compares against AutoBot's SLM layer.

**This is not an OS question.** None of the work below is about choosing, targeting or resembling an
operating system, and nothing here changes our architecture. These are lifecycle-management *methods*
— how a control plane declares what it manages, gates what it loads, verifies what it deployed, and
updates without dropping the workload. We take the methods and apply them our way, to be superior
**in our field**: a control plane for AI agent workloads, where an interrupted node is an interrupted
workflow.

**Reference works studied** (2026-09-08, from upstream docs and repos):

| Work | What it is | Maturity signal |
|---|---|---|
| **Cockpit** | systemd-native web console, Red Hat sponsored, LGPL | v367 shipping; default web console of several enterprise distros |
| **Webmin** | Perl module-based admin panel with its own embedded web server | ~25.7k commits, 116 bundled modules, ~1M installs/yr |
| **Virtualmin** | hosting/provisioning layer built as Webmin modules | ~150k installs; ~200-verb CLI + HTTP API |
| **oVirt** | virtualization manager: an engine plus Ansible-driven host deploy | **AutoBot's own lineage** — the SLM's Ansible deployment approach was inspired by its downstream (maintainer, 2026-09-08) |
| *a live-patching vendor stack* | fleet automation + rebootless patching, kept unnamed | methods only; the implementation is vendor kernel work |
| *a commerce platform's integrity checker* | per-release published checksum manifests, kept unnamed | see the addendum |

---

## What It Is

Four bodies of work that solve the same problem — *give an operator a browser-driven way to
administer a Linux host and its services* — from opposite ends of the design space. Cockpit is a
thin, stateless projection of the host's own D-Bus/systemd APIs, holding no state of its own and
running nothing when nobody is looking at it. Webmin is the opposite: a self-contained Perl
application server with its own HTTP server, its own user database, its own ACL engine, and 116
service-specific modules that parse and rewrite native config files directly. Virtualmin layers a
provisioning domain model (virtual servers, templates, plans, features) on top of B and exposes it
through a CLI and an HTTP API that are the same surface rendered twice. oVirt is the fleet view: an
engine that holds cluster state, Ansible-driven host deploy, and a host lifecycle in which
"update this host" means *drain it first*. A fifth reference contributes patching methods only. All four are mature, long-lived, and
in production at scale — none is a research prototype.

## Architecture & Key Patterns

**Cockpit — three-process privilege split, zero-resident-cost service**

- `ws` (web service, TLS, auth) ↔ `session` (PAM) ↔ `bridge` (per-user, in the user's real login
  session). The bridge has *exactly* the privileges the same user would get over SSH — nothing is
  granted by the console itself.
- systemd **socket activation** on :9090. Nothing runs until a browser connects; `ws` exits after
  10 min idle, `bridge` exits at logout, the browser self-disconnects after 30 s of silence.
- **No private user store.** Authentication is the host's own PAM stack (`/etc/pam.d/<console>`),
  with Kerberos SSO and certificate/smart-card as drop-ins. `MaxStartups` caps concurrent logins
  the way an SSH daemon does.
- **Escalation is session-scoped and user-revocable at runtime.** polkit/sudo grants root at login
  if the user could get it at a shell; the operator can *drop* root mid-session from the top bar
  and take it back. Per-channel flag `superuser: "require" | "try"` decides privilege per
  operation, not per session.
- **Typed channels over one WebSocket.** The browser opens channels with a declared `payload` type
  (spawn, dbus, file, http, metrics, stream); a JS shim wraps each into an ergonomic API. Privilege
  and binary-ness are channel properties, not global ones.
- **Features delegate, they do not reimplement.** systemd, NetworkManager, storaged, firewalld,
  realmd, SELinux, tuned, PCP (metrics), and a distro-independent package-update D-Bus API each
  back one UI page. The console owns no service logic.

**Cockpit — the package (plugin) contract**

- A package is a directory + `manifest.json`, discovered along XDG data dirs in fixed precedence:
  `~/.local/share/…` → `/usr/local/share/…` → `/usr/share/…`, **first hit wins**.
- Manifest fields worth stealing: `requires: {"<console>": "120"}` (minimum host version — package
  is simply not usable below it), `conditions` predicates (`path-exists`, `path-not-exists`, and a
  nested `any`) so a package self-suppresses when its backing service is absent, `priority` for
  same-name conflicts, `preload` for components loaded at login instead of on navigation,
  per-package `content-security-policy` override (a strict CSP is the default and any override is
  re-merged with the mandatory directives), and menu placement with **documented numeric ordering
  bands** (system info 10, logs 20, subsystems 30–40, workloads 50–60, implementation details
  70–100).
- Search metadata is declarative: `keywords` with `matches`/`goto`/`weight`/`translate` per entry,
  and per-page `docs` URL lists.
- **Cache policy is a development affordance:** system packages are cached aggressively behind a
  content checksum; packages in the user's home dir are never cached, so the edit-reload loop needs
  no cache busting and no restart.
- Fleet/multi-host was **deprecated at v322** and is off by default: remote hosts were reached by
  SSH from `ws`, but their JS ran in the *same browser context* as the local host, so any remote
  host could inject code with primary-session privileges. The fix shipped was a config switch
  (`AllowMultiHost=false`) and a warning, not isolation.

**Webmin — self-contained module panel**

- Embedded Perl HTTP server on :10000 handles TLS, sessions, auth, ACL and routing in-process; no
  system web server, no external app server, no database.
- A module is a directory; **only `module.info` is mandatory** (description, version, supported OS
  list, category, `hidden` flag). Everything else — CGI entry points, a `-lib.pl` library, `lang/`,
  `help/` — is convention.
- **Per-module ACL as a plugin contract:** a module that wants access control ships
  `acl_security.pl` exposing a form-render and a save function, plus a `defaultacl` file of
  `name=value` defaults that are deliberately *permissive* so the master admin is never restricted
  by a module's own defaults.
- Distribution is a tarball of the directory, installable from the UI, with generator scripts that
  wrap the same directory as a native `.rpm` or `.deb`.
- **Action log:** every state-changing page writes an audit record; pages that change nothing write
  nothing. Optional recording of the *file diffs* themselves turns the audit log into a rollback
  source.
- **Config backup is a declared capability, not a snapshot:** each module declares which config
  files it owns; a central module collects those declarations and backs up / restores per-module
  sets to a local or remote destination.

**Virtualmin — feature lifecycle contract + one surface, three renderings**

- The provisioned unit is a hash of **enabled feature codes** (`web`, `mail`, `dns`, `<login>` …).
  Each pluggable feature is a Webmin module containing `virtual_feature.pl` that implements a
  fixed lifecycle: `feature_check` (dependency self-test at *registration* time) →
  `feature_depends` / `feature_clash` / `feature_suitable` (pre-flight refusal with a human
  message) → `feature_setup` / `modify` / `enable` / `disable` / `delete` → `feature_backup` /
  `feature_restore` (**every feature backs up its own state**) → `feature_validate` (post-hoc drift
  check) → `feature_links`, plus per-feature template and limit form hooks.
- **Shape and quota are separate objects:** a *server template* defines what a provisioned unit
  looks like; an *account plan* defines its limits. Same feature set, different envelope.
- CLI: ~200 `verb-noun` operations, exit-code contract (0/non-zero), `help` per command,
  `--multiline` to switch list output from human to machine-readable.
- **Remote API is the CLI, rendered:** one CGI endpoint takes `program=<cli-verb>` plus the same
  parameters, with `json=1` / `xml=1` / `perl=1` output switches, authenticated against the same
  user store, restricted to the master admin. No parallel API model to keep in sync.
- **Configuration history** with `list-config-revisions` / `restore-config-revision` — config is
  versioned and rollback is a first-class command.
- Pre- and post-modification hook scripts and template variables give operators an extension point
  that needs no plugin at all.

**oVirt — host lifecycle where updating means draining first**

From the Upgrade Manager design and the administration/upgrade guides:

- **Update availability is host state, not a report.** `GET /hosts/{id}` returns
  `<updates_available>true</updates_available>` — the fleet view answers "which hosts need
  attention" by reading host state, and the upgrade is an action on the same resource
  (`POST /hosts/{id}/upgrade`).
- **The drain-update-return cycle is one operation.** Upgrading a host in `Up` status sets it to
  **maintenance mode**, which triggers migration of its workloads to other hosts in the cluster;
  packages are then installed via the Ansible-driven host deploy; the host is brought back up. If
  workloads are still running, the operator is warned before proceeding.
- **The update set is scoped by policy.** `PackageNamesForCheckUpdate` holds the system-required
  packages that define the role; `UserPackageNamesForCheckUpdate` is a mergeable, wildcard-capable
  operator list. "An update is available" therefore means *the packages that matter to this role*
  changed — not "the package manager has 340 upgradable things". `HostPackagesUpdateTimeInHours`
  makes the check cadence configuration.
- **Rolling fleet upgrade composes from the per-host cycle.** Host by host: maintenance → upgrade →
  activate, with per-host status visible so the operator can see how far the fleet has got.
- **The engine's own maintenance is a distinct mode.** Global maintenance mode exists for operations
  that require stopping the engine itself — the control plane's own update is not pretended to be
  the same problem as a managed host's.


## Notable Implementation Details

1. **Privilege as a per-operation property.** Cockpit's `superuser: "require" | "try"` per channel
   means a page can attempt a privileged read and gracefully degrade, instead of the whole session
   being root-or-nothing. Paired with runtime drop/regain, the blast radius of an idle admin tab is
   an operator-controlled variable.
2. **Plugin conditions beat plugin priority.** Cockpit explicitly documents `conditions`
   (`path-exists`) as *preferable* to `priority` — a package that self-suppresses when its backing
   service is missing is more predictable than a package that wins a numeric fight.
3. **Ordering bands as documented API.** Publishing "logs = 20, subsystems = 30–40" makes third-party
   menu placement deterministic without a registry.
4. **Dev-mode cache exemption by location.** "Packages under `$XDG_DATA_HOME` are never cached" is a
   one-line rule that removes an entire class of plugin-development friction.
5. **`feature_check()` at registration, not at use.** Virtualmin validates a plugin's dependencies
   when the plugin is enabled, so the failure surfaces in the admin's hands, not in a provisioning
   run at 3 a.m.
6. **Backup/restore as a per-feature interface.** Because each feature implements its own
   backup/restore, adding a feature never requires touching a central backup routine — the thing
   that usually rots.
7. **One API definition rendered three ways.** Virtualmin's HTTP endpoint dispatches to CLI verbs by
   name, so CLI, HTTP+JSON and HTTP+XML cannot drift.
8. **Audit log that records the diff, not just the verb.** Optional file-change capture is what
   turns "who changed Apache" into "undo what they changed".
9. **Socket activation as the security posture.** Zero processes when unattended is both a resource
   and an attack-surface argument, and it costs one systemd unit.
10. **Tripwires in patched code.** Turning each backported fix into a detection point converts a
    patch pipeline into a telemetry pipeline for free.

## Strengths

- **Cockpit:** minimal trust surface (no own user store, no own privilege grant, no resident
  process); a genuinely well-specified plugin manifest; feature pages that are thin over stable
  system APIs, so they age well.
- **Webmin:** installs anywhere with a Perl interpreter and nothing else; 116 modules of
  accumulated service knowledge; ACL granularity per user per module that few modern panels match.
- **Virtualmin:** the lifecycle contract is the cleanest part — a provisioning system where adding a
  capability means implementing a documented set of ~20 functions, backup included; CLI/API parity
  by construction; config revisions with rollback.
- **oVirt:** update availability is part of host *state*, the update set is scoped by policy rather
  than being "everything the package manager offers", and the drain-update-return cycle is a single
  first-class operation that composes into a rolling fleet upgrade.

## Weaknesses / Limitations

- **Cockpit** has no fleet story any more — multi-host was deprecated because remote code shared
  the browser context, and the shipped answer was to turn the feature off. It is also strictly a
  *projection*: no workflow, no scheduling, no history, no cross-host aggregation. Its plugin model
  assumes OS packages as the distribution channel; there is no in-UI install/update of packages.
- **Webmin** carries a large legacy surface: CGI-per-page, an embedded Perl HTTP server that is
  its own perpetual security responsibility, and modules that parse and rewrite native config files
  by hand — a maintenance liability across distro versions. Its own user store is a second identity
  system to secure and rotate.
- **Virtualmin** inherits all of B's substrate, plus a Pro/GPL feature split, plus an HTTP API that
  is CGI-with-query-parameters and master-admin-only — no per-token scoping, no rate model, and
  credentials in the URL unless the caller remembers to POST.
- **oVirt** carries the weight of a full virtualization manager: its drain step is VM live migration,
  which has no counterpart for a stateless role, and its engine is a large stateful component whose
  own maintenance needs a global maintenance mode. The *method* transfers; the machinery does not.
- The **live-patching stack**'s attractive halves are gated behind paid support tiers, and its
  implementation is vendor kernel engineering — methods only, as noted.

## Visible vs Hidden Metrics

**Visible (advertised, mostly self-reported):**

- Webmin: ~1M installs/yr, 116 modules, 25.7k commits — a scale claim, not a quality claim.
- Virtualmin: ~150k installs, ~200 CLI verbs, "nearly all UI functions available from the CLI".
- Cockpit: version 367 and default-shipped by multiple enterprise distros — the strongest
  independently-verifiable signal in the set, since inclusion is a third party's judgement.
- oVirt: rolling cluster upgrade with per-host task status — documented design, long in production.
- The live-patching stack: rebootless patching and blocked privilege-escalation attempts — vendor-reported.

**Hidden (the costs an adopter inherits):**

- **Cockpit's model is only cheap on the OS it assumes.** Its "no state, no user store, delegate
  to D-Bus" elegance *is* systemd + polkit + PackageKit + PCP. Adopting the pattern without those
  substrates means reimplementing the substrate, which is where the cost actually lives.
- **Cockpit's plugin contract assumes OS-package distribution** — the filesystem-precedence
  discovery model has no answer for install/upgrade/rollback of a plugin from within the product.
- **Webmin/Virtualmin's self-containment is a permanent security payroll:** a bespoke HTTP server, a
  bespoke session layer, a bespoke ACL engine and a second user store are four things that must be
  patched forever and audited separately from the platform's own auth.
- **Virtualmin's lifecycle contract has a real cost:** ~20 functions per feature, and every one of
  them is a place a plugin author can silently do nothing. The contract only pays off with a
  conformance test per hook.
- **The CLI-as-API trick has a hidden ceiling:** parity is free, but so is inheriting the CLI's
  string-typed parameters, its exit-code-only error model, and its lack of per-scope authz.
- **The live-patching stack's implementation is not portable, but its policy is.** The transferable
  residue is *policy* — patch without interrupting the workload, treat each patch as a detection
  point — and policy costs nothing to adopt.
- **oVirt's drain step assumes a migratable workload.** Live migration of a VM is not the same
  problem as handing off a role; adopting the method means solving the hand-off, not copying it.

**Weighing:** the transferable value is concentrated in the *contracts*, not the runtimes. Console
A's manifest (`requires` / `conditions` / `priority` / `preload` / declared ordering / per-package
CSP / dev-mode cache exemption) and Virtualmin's feature lifecycle (`check` → `depends`/`clash` →
`setup`/`modify`/`disable`/`delete` → `backup`/`restore` → `validate`) are both cheap to adopt and
substrate-independent. Everything with a heavy hidden cost — the embedded HTTP server, the second
user store, the D-Bus-shaped feature layer, the CGI remote API, the vendor kernel work — is either
already solved differently in AutoBot's stack or not portable at all. A comparison pass should
therefore be scoped to the contracts and the operator-facing policies (audit-with-diff, config
revisions with rollback, per-feature backup, patch-without-restart), not to any of the four
runtimes.

---

*Phase 2 (AutoBot comparison) not started — awaiting approval.*

---

# Phase 2 — Comparison against the SLM layer

Scope: `autobot-slm-backend/` (443 Python modules), `autobot-infrastructure/*/manifest.yml`
(13 role manifests), `autobot-slm-agent/`, `autobot-slm-frontend/`. Every row below carries the
already-exists audit that produced its verdict.

**Lineage note (from the maintainer, 2026-09-08):** the SLM's Ansible deployment approach was
itself inspired by oVirt's downstream — the engine-plus-Ansible-host-deploy shape. So the comparison
below is between two descendants of overlapping ideas, not between AutoBot and something foreign.

## Already-exists audit — what was read

| Reference concept | AutoBot files checked | Present? |
|---|---|---|
| Plugin/package manifest | `models/manifest.py` (288 L, `RoleManifest`), `services/manifest_loader.py` (183 L), 13 × `autobot-infrastructure/*/manifest.yml` | **Yes**, richer in ops fields |
| Declared conflicts | `models/manifest.py:145-159` `ManifestCoexistence` (`conflicts_with` / `warns_with` / `compatible_with`) | **Yes**, 3 severities vs the reference's 1 |
| Declared dependencies | `models/manifest.py:210` `depends_on`; `models/manifest.py:183` `system_dependencies`; `models/manifest.py:184` `python_version` | **Yes** |
| Start ordering | `models/manifest.py:82` `ManifestService.start_order` | **Yes**, per-service |
| Min-platform-version gate | grep `min_version|schema_version|api_version|requires_slm` across `models/`, `services/` | **No hits — gap** |
| Self-suppressing conditions | `ManifestLoader._load_from_disk`, `models/manifest.py` | **No** — a missing dep is a runtime failure, not a skip |
| Discovery precedence / dev override | `services/manifest_loader.py:29-31` — one fixed path `$AUTOBOT_BASE_DIR/autobot-infrastructure/<role>/manifest.yml` | **No** — single path, no override dir |
| Per-feature backup/restore | `services/backup.py` (`BackupService`, central; Redis/PostgreSQL only) | **Central**, not per-role |
| Post-hoc validation / drift | `services/drift_checker.py` (checksum diff, code_source vs deployed) | **Yes**, checksum-based |
| Audit log | `models/database.py:790` `AuditLogCategory`, `:840` `AuditLog` → `slm_node_audit_logs` | **Yes** (records `request_body`, not on-disk delta) |
| Config revisions + rollback | `services/blue_green.py`, `api/blue_green.py`, `api/maintenance.py` | **Deployment** rollback yes; **config-file** revisions no |
| CLI ↔ API parity | `scripts/autobot-admin.py` (119 L, **one** subcommand: `reset-password`) | **No — gap** |
| Privilege escalation model | `services/step_up_auth.py` (`auth_time`/`iat`, `SLM_STEP_UP_MAX_AGE_SECONDS`, default 900 s), `services/local_admin_socket.py` | **Yes**, different shape |
| Socket activation | `services/local_admin_socket.py` — `sd_listen_fds()`, `autobot-slm-self-update.socket`, `SocketMode/User/Group` | **Yes, already** |
| Per-page CSP override | `middleware/security_headers.py:127`, `ansible/roles/slm_manager/templates/autobot-security-headers-{strict,iframe-host}.conf.j2` | **N/A** — one SPA, no third-party packages |
| OS-independent update abstraction | `api/updates.py`, `ansible/check-system-updates.yml`, `docs/archives/plans/2026-02-27-system-updates-design.md:88` | **Yes**, already borrowed |
| Reboot policy on update | `models/manifest.py:26` `RebootStrategy`, `:138` `ManifestSystemUpdates` | **Yes**, declarative |

## What We Can Adopt

### 1. A minimum-platform-version gate in the role manifest — **adopt**

- **From:** the package manifest's `requires: {"<console>": "120"}` — a package is simply not usable
  on an older host, checked at load, not at use.
- **Applies to:** [models/manifest.py](autobot-slm-backend/models/manifest.py) (`RoleManifest`),
  enforced in [services/manifest_loader.py](autobot-slm-backend/services/manifest_loader.py).
- **Audit:** grep for `min_version|min_slm|schema_version|api_version|requires_slm` across
  `autobot-slm-backend/models/` and `services/` returned **no hits**. `RoleManifest.version`
  (`models/manifest.py:167`) is the *role's own* version and is informational only — nothing reads
  it to gate anything.
- **Visible benefit:** a manifest written against a newer SLM schema fails loudly at load with the
  role named, instead of silently losing whichever fields the older loader does not know.
- **Hidden cost:** low. One optional field plus one comparison in `_load_from_disk`; the risk is
  operators pinning it too tight and blocking their own upgrades, mitigated by making it optional.
- **Effort:** trivial.

### 2. Self-suppressing conditions instead of hard failure — **adopt-with-conditions**

- **From:** manifest `conditions: [{path-exists: …}, {path-not-exists: …}, {any: [...]}]`, documented
  as *preferable to* numeric priority.
- **Applies to:** `RoleManifest`, `ManifestLoader.get_manifest`, and the reconcile loop in
  [services/reconciler.py](autobot-slm-backend/services/reconciler.py).
- **Audit:** `ManifestCoexistence` (`models/manifest.py:145`) declares conflicts *between roles*;
  `system_dependencies` (`:183`) declares apt packages. Neither expresses "this role is
  inapplicable on this node, skip it quietly" — an absent dependency surfaces as a deploy/health
  failure.
- **Visible benefit:** optional roles (`_OPTIONAL_ROLES`, `services/role_registry.py:300`) stop
  producing red health for nodes that were never meant to run them.
- **Hidden cost:** real. A silent skip is indistinguishable from a silent misconfiguration — the
  reference work's own guidance is only safe because a skipped package is *visible* in the package
  list. Condition: any skip must be surfaced as an explicit `skipped(reason)` state in the node
  view, never as absence.
- **Effort:** moderate.

### 3. Per-role backup/restore as a manifest contract — **adopt-with-conditions**

- **From:** `feature_backup(domain, file, opts)` / `feature_restore(...)` — every feature backs up
  its own state, so adding a feature never edits a central backup routine.
- **Applies to:** [services/backup.py](autobot-slm-backend/services/backup.py) + `RoleManifest`.
- **Audit:** `BackupService` (`services/backup.py:65`) is central and its docstring scopes it to
  "stateful services (Redis, PostgreSQL, etc)". A role with state outside those two — ChromaDB,
  model caches, `/etc/autobot/*.env` — has no declared backup path. `ManifestSecrets` (`:110`)
  declares secret *ownership* already, which is the natural place to hang it.
- **Visible benefit:** backup coverage becomes a property of the manifest set, auditable by
  counting roles with no backup declaration.
- **Hidden cost:** the reference contract's weakness is that ~20 hook functions give a plugin
  author 20 places to silently do nothing. Condition: ship it as *declarative* (`backup: {paths,
  command, restore_command}`) rather than as code hooks, plus a conformance check that every role
  either declares backup or declares `stateless: true`.
- **Effort:** significant.

### 4. Audit entries that carry the resulting delta, not just the request — **adopt**

- **From:** the action log that optionally records the *file changes*, which is what makes an audit
  entry a rollback source rather than a receipt.
- **Applies to:** [models/database.py:840](autobot-slm-backend/models/database.py#L840) (`AuditLog`)
  and the deploy path.
- **Audit:** `AuditLog` already has actor, category, action, `resource_type`/`resource_id`,
  `request_method`/`request_path`, sanitized `request_body`, `success`, `error_message`,
  `extra_data`. What it records is the **intent** (the API call). `drift_checker.py` computes
  checksum deltas but stores no previous content, so nothing on either side can answer "what did
  this deployment actually change on disk".
- **Visible benefit:** "which deploy changed this file" becomes answerable; drift becomes
  attributable instead of merely detectable.
- **Hidden cost:** unbounded growth and a new secret-leakage surface — config files contain
  credentials, and `request_body` is sanitized today precisely for that reason. Store checksums +
  path lists by default and full content only behind an explicit opt-in with retention.
- **Effort:** moderate.

### 5. CLI/API parity by dispatching one verb table — **adopt-with-conditions**

- **From:** ~200 `verb-noun` CLI operations, and an HTTP endpoint that takes `program=<cli-verb>`
  plus the same parameters with `json=1`, so the two surfaces cannot drift.
- **Applies to:** [scripts/autobot-admin.py](autobot-slm-backend/scripts/autobot-admin.py) against
  the ~60 routers in `autobot-slm-backend/api/`.
- **Audit:** `autobot-admin.py` is 119 lines with a single subcommand, `reset-password`
  (`scripts/autobot-admin.py:109`). Every other operation — node management, deploy, code-sync,
  updates, blue-green — is reachable only through the authenticated HTTP API or the recovery
  endpoint. An operator on the host with a broken frontend has `/recovery` and the self-update Unix
  socket, and nothing else.
- **Visible benefit:** scriptable operations and a working break-glass path when the SPA is down.
- **Hidden cost / direction reversed:** the reference builds the HTTP API *on top of* the CLI, which
  inherits string-typed parameters, an exit-code-only error model and no per-scope authz — all
  things the SLM already does better with FastAPI + Pydantic + RBAC. **Condition: invert it.**
  Generate the CLI *from* the existing OpenAPI schema (`scripts/dump_openapi.py` already exists) and
  route it over the Unix-socket listener that `services/local_admin_socket.py` established, so the
  CLI inherits the typed models and the audit log instead of bypassing them.
- **Effort:** moderate.

### 6. The patching stack's *methods* — **adopt (three of them)**

**Framing correction (maintainer, 2026-09-08):** this was never about an operating system. We keep
our architecture; we take the methods that make a lifecycle manager good and apply them our way, to
be superior **in our field** — a control plane for AI agent workloads, where an interrupted node is
an interrupted workflow, not a restarted web server. Stripped of the vendor kernel implementation,
the patching stack yields three portable methods, and the audit found all three are gaps here.

**6a. A fix leaves a tripwire, not only a regression test.** The method behind "known exploit
detection": when a defect is patched, leave an assertion at the fixed condition that fires *in
production* if it recurs, emitting an event. **Audit:** already proven here on one narrow subject —
`services/security_posture_auditor.py` (#11224) is a recurring background job recording interface-
exposure regressions as `SecurityEvent` rows, *"so exposure regressions are surfaced proactively
instead of noticed reactively"*. Loop pattern, storage and model all exist; what is missing is the
generalisation to a named invariant registry. Every other fixed defect in this repo leaves a CI test
and nothing that watches production. → **#16035**

**6b. Apply the update without dropping the workload.** The portable half of "rebootless" is the
policy, not the kernel. **Audit:** both halves exist and are *not connected* — `models/manifest.py:26`
`RebootStrategy` and `:138` `ManifestSystemUpdates.reboot_strategy` are declared by every role, while
`api/updates.py` hardcodes `"auto_reboot": "false"` at `:163` and `:949`, so the declared strategy is
never read. Meanwhile `services/blue_green.py` already implements role borrowing with
`post_deploy_monitor_duration` and health-gated `auto_rollback` — the drain-and-hand-off machinery,
built for deploys. `grep blue_green api/updates.py` → no hits. → **#16036**

**6c. Exposure is per-node and per-advisory, not a package count.** **Audit:** `grep -riE '\bcve\b'`
across `autobot-slm-backend/{services,api,models}` → **zero hits**. `api/updates.py:367`
`_classify_severity(pkg_name, security_packages, repo)` infers severity from the source-repo string —
which is exactly what the 2026-02-27 design adopted ("parse source repository to tag security vs
regular updates") and the limit of it. No advisory identity anywhere. → **#16037**

### 7. oVirt's host-update lifecycle — **adopt (three deltas)**

Our own lineage, which makes this the least speculative row in the table: the SLM's Ansible
deployment approach came from oVirt's downstream. The engine-plus-host-deploy half was taken; the
*host update lifecycle* half was not.

**7a. Update availability belongs on the node resource.** oVirt returns `updates_available` on
`GET /hosts/{id}` and accepts `POST /hosts/{id}/upgrade`. **Audit:** `models/database.py:142`
`Node` carries no updates-available field; update state lives in separate `UpdateInfo` (`:383`) and
`UpdateJob` (`:411`) tables reached through `api/updates.py`. Answering "which nodes need attention"
therefore means joining a side table rather than reading node state. *Minor* — the information
exists, the shape differs. Folded into 7b rather than filed alone.

**7b. Drain before update; make `reboot_strategy` live.** Covered by item 6b above and filed as
**#16036**; oVirt supplies the concrete shape — maintenance mode triggers hand-off, then the deploy
runs, then the node returns to service, and the same cycle composes host-by-host into a **rolling
fleet upgrade** with per-host status. **Audit:** `grep -niE 'rolling|serial' api/updates.py
services/deployment.py` → no hits; there is no rolling fleet update. `services/blue_green.py` has
the role-borrowing hand-off but it is wired only to deployments.

**7c. Scope the update set to what defines the role.** This is the cheapest win in the whole
document, because *the declaration already exists*. **Audit:** `api/updates.py` reports on the full
apt upgradable set — `"Found {total_packages} upgradable packages across {nodes_checked} nodes"`
(`:596`, `:608`) — and `_run_update_job` runs "apt upgrade all on a node" (`:977`, `:996`). No
reference to the manifest anywhere in the file. Yet `models/manifest.py:183` `system_dependencies`
already declares, per role, the apt packages that role requires. oVirt's two-list policy
(system-required + a mergeable operator list with wildcards) maps onto it directly.

- **Visible benefit:** "this node has updates" starts meaning *something that matters to what this
  node runs*, instead of a number dominated by packages no role depends on. Severity classification
  gets a smaller, more meaningful set to work on.
- **Hidden cost:** genuine — a scoped view can hide a security update to a package no role declares
  but every node still runs (openssl, glibc). Condition: scoped is the **default view**, never the
  only one; the full set stays reachable, and security-classified updates are never filtered out by
  scope.
- **Effort:** trivial to moderate.

**Not adopted:** the live-patching *implementation* — vendor kernel engineering behind a support
contract. That is the only part of any reference work here that is platform-bound, and none of the
three methods above needs it.

## What We Already Do Better

| Area | AutoBot | The reference works |
|---|---|---|
| **Manifest richness** | `RoleManifest` declares deploy source/destination, systemd units with `start_order`, ports with `public`/`loopback_only`, health endpoint + interval/timeout/retries/expected status, **owned vs shared secrets**, TLS auto-rotation with `rotate_days_before`, apt update policy + reboot strategy, and 3-level coexistence | Cockpit's manifest is UI-placement metadata plus load gating; it declares no ports, no health, no secrets, no update policy |
| **Conflict expressiveness** | `conflicts_with` / `warns_with` / `compatible_with` — hard, soft, and explicit-OK | `feature_clash()` returns an error string or nothing; one severity |
| **Deployment rollback** | Blue-green with role borrowing, `post_deploy_monitor_duration`, and `auto_rollback` on health failure (`services/blue_green.py`) | Virtualmin versions *config* and can restore a revision; none of the four has a health-gated automatic deployment rollback |
| **Drift detection** | Checksum comparison of code_source vs deployed, extension-scoped (`services/drift_checker.py`) — catches *any* manual patch | `feature_validate()` is per-feature, hand-written, and only as thorough as its author |
| **Auth substrate** | OIDC/SSO with JWKS verification, MFA, SCIM, RS256 denylist, token denylist, step-up re-auth with a configurable max age | Webmin/Virtualmin run a bespoke user store and session layer; Cockpit delegates to PAM but has no step-up concept at all |
| **API surface** | ~60 typed FastAPI routers, OpenAPI-documented, RBAC-gated | Virtualmin's remote API is one CGI taking a program name as a query parameter, master-admin-only, credentials in the URL unless the caller chooses POST |
| **Fleet** | Multi-node is the *premise* — inventory builder, reconciler, code distributor, agent per node | Cockpit **deprecated** multi-host at v322 and defaults it off; the fleet story moved to a separate AWX-derived product |
| **Isolation** | Nodes are reached over SSH/Ansible from the control plane; no remote code enters the operator's browser | Cockpit's deprecation exists precisely because remote host JS ran in the primary session's browser context |
| **Socket activation** | Already in use for the privileged self-update path, with systemd owning the socket's permissions before the process starts | Cockpit applies it to the whole web service; Webmin/Virtualmin run a permanently-listening bespoke HTTP server |

## Gaps & Opportunities — prioritized

1. **Two sources of truth for role shape** *(highest impact — this is a defect, not an adoption
   gap)*. `services/role_registry.py` `DEFAULT_ROLES` (Python dicts, consumed by `api/deployments.py`,
   `api/code_sync.py`, `api/roles.py`, `api/blue_green.py`, `api/setup_wizard.py`,
   `services/inventory_builder.py`) and `autobot-infrastructure/*/manifest.yml` (consumed by
   `services/reconciler.py`, `api/nodes.py`) describe the same roles with different identifiers and
   overlapping fields. For the backend role: `name: "backend"` vs `role: autobot-backend`;
   `health_check_port: 8443` + `health_check_path` vs `health.endpoint`; `source_paths` +
   `target_path` vs `deploy.source` + `deploy.destination`; and `systemd_service: "autobot-backend"`
   (**one** unit) vs `services:` declaring **two** (`autobot-backend`, `autobot-celery`). The deploy
   path and the reconcile path can therefore disagree about what a role *is*. → filed as an issue.
2. **No minimum-platform-version gate** on manifests (item 1 above). Cheap, and the schema is
   already versioned informally.
3. **Backup coverage is not a declared property** of a role (item 3). Today "is this role's state
   backed up?" is answerable only by reading `BackupService`.
4. **No operator CLI** beyond password reset (item 5). The break-glass path is `/recovery` plus one
   Unix socket; everything else needs a working SPA and a session.
5. **Audit entries cannot answer "what changed on disk"** (item 4).
6. **Manifest cache has no dev-mode exemption and a hardcoded TTL** —
   `services/manifest_loader.py:32` sets `_CACHE_TTL = 300` as a literal, against the project rule
   that TTLs come from env-var-backed module constants (the same file already env-backs
   `AUTOBOT_BASE_DIR` at `:29`). A manifest edit is also invisible for up to 5 minutes with no way
   to bypass. → filed as an issue.

## Specific Files Affected

| File | Change |
|---|---|
| [autobot-slm-backend/models/manifest.py](autobot-slm-backend/models/manifest.py) | Add `requires_slm: str \| None` (min platform version); optional `conditions` list; optional `backup: ManifestBackup` or `stateless: bool` |
| [autobot-slm-backend/services/manifest_loader.py](autobot-slm-backend/services/manifest_loader.py) | Enforce `requires_slm` at `_load_from_disk`; evaluate `conditions`; env-back `_CACHE_TTL`; add a no-cache dev path |
| [autobot-slm-backend/services/role_registry.py](autobot-slm-backend/services/role_registry.py) | Converge onto the manifests as the single role SSOT; `DEFAULT_ROLES` becomes a projection, not a parallel declaration |
| [autobot-slm-backend/services/backup.py](autobot-slm-backend/services/backup.py) | Drive backup targets from manifest declarations instead of a hardcoded stateful-service list |
| [autobot-slm-backend/models/database.py](autobot-slm-backend/models/database.py) | Extend `AuditLog.extra_data` (or a sibling table) with the changed-path + checksum delta of a deploy |
| [autobot-slm-backend/scripts/autobot-admin.py](autobot-slm-backend/scripts/autobot-admin.py) | Generate subcommands from the OpenAPI schema; transport over the existing Unix-socket listener |
| [autobot-slm-backend/services/reconciler.py](autobot-slm-backend/services/reconciler.py) | Surface condition-skipped roles as an explicit `skipped(reason)` state |

---

## Addendum — a fifth reference: vendor-published integrity manifests

Added 2026-09-08 on the maintainer's pointer.

**Checker E** — the core-integrity checker of a widely-deployed self-hosted commerce platform.
Verified from its own docs and issue tracker; the parts marked *unverified* could not be confirmed
from primary sources in this pass.

**What it does:** the platform's release infrastructure publishes, per release, a manifest listing
every file in the distributed archive together with that file's checksum. An admin page (Advanced
Parameters → Information, "list of changed files") walks the installed tree, recomputes SHA-1 per
file, and reports which core files no longer match the released original. The upgrade path consumes
the same manifests. *Unverified:* whether the updater performs a genuine three-way comparison
(shipped-original vs on-disk vs target-release) to leave operator-modified files alone, and the
exact missing/altered/extra category split.

**The transferable idea — the reference is external to the installation.** Checker E compares the
deployed tree against a **manifest published by the release authority**, not against a copy of the
source sitting on the same machine. That distinction is the whole value: it detects tampering of
the *reference itself*, and it verifies a node whose local source tree is absent, stale, or
compromised.

### Already-exists audit

[services/drift_checker.py](autobot-slm-backend/services/drift_checker.py) — read in full at the
comparison level: `_collect_checksums` (`:726-727`), `compute_drift` (`:735-778`),
`build_drift_report` (`:781-813`).

AutoBot's drift checker is **two-way**: `src_path` (the `code_source` checkout on the SLM host) vs
`dep_path` (the deployed directory on the node). It already carries refinements none of the five
reference works have:

- **Status classification exists:** `source_only`, `untracked` (deployed-only — deliberately
  excluded from `drift_detected` at `:804`, because an extra file is not drift), and modified.
- **Expected-drift exclusions:** `_is_expected_drift(rel_path, component, owned)` (`:739`) so
  operator-owned paths do not report forever.
- **Render-invariant comparison** for Jinja2-templated components (`_rendered_file_drift`, `:746`;
  #12886) — a rendered file is compared against its rendering, not byte-for-byte against a template.
- **Per-component extension scoping** (`comparable_extensions`, `:74`) so compiled output and
  `node_modules` are never compared, only source (#10120).
- **Documented blocked components** with the reason recorded inline (`:134-158`) rather than a
  silent skip.

**Verdict on the classification and exclusion machinery: we already do this better.** Checker E
reports "these files differ"; AutoBot reports *which kind* of difference, excludes the kinds that
are legitimate, and names the components it cannot yet compare and why.

### The one delta worth adopting — **adopt-with-conditions**

**A signed, release-pinned checksum manifest as the drift reference.**

- **Gap:** AutoBot's reference is the local `code_source` checkout (`DEFAULT_REPO_PATH`, imported
  from `services/git_tracker.py` at `drift_checker.py:22`). If that checkout is stale, partially
  synced, or edited on the SLM host, drift is computed against the wrong baseline — and the
  checker cannot tell you so. `git_tracker.py` knows the commit, but the checksum comparison does
  not bind to it.
- **Change:** emit a checksum manifest per deployed commit (path → digest, per component) as a
  build/deploy artifact — `services/deploy_artifacts.py` is already the artifact seam — and have
  `compute_drift` compare the node against *that pinned manifest*, falling back to the live
  checkout only when no manifest exists for the deployed commit.
- **Visible benefit:** drift becomes attributable to a specific commit; a tampered or stale SLM-side
  source tree is detected instead of silently becoming the baseline; and a node can be verified
  without the checkout being present at all.
- **Hidden cost:** a second artifact to generate, store, garbage-collect and keep in step with the
  deploy — and a manifest that goes missing turns a working check into a fallback path, which is
  exactly how integrity checks quietly stop checking. Conditions: (a) the fallback must report
  itself as *unverified baseline*, never as "no drift"; (b) manifest generation belongs in the same
  step that produces the deploy, so it cannot drift from it; (c) sign or at minimum checksum the
  manifest itself, or the tampering problem simply moves one level up.
- **Effort:** moderate.

This pairs directly with **item 4** above (audit entries carrying the on-disk delta): a per-commit
checksum manifest is the missing "before" side that makes a deploy's change set recordable and
attributable.

---

## Filed

Umbrella **#16028** — *Adopt external host-lifecycle methods into the SLM layer*, with nine children
linked as native GitHub sub-issues.

| Wave | Issue | Item |
|---|---|---|
| 1 | #16029 | Minimum-platform-version gate (`requires_slm`) |
| 1 | #16030 | Self-suppressing `conditions` + explicit `skipped(reason)` state |
| 1 | #16032 | Per-commit checksum manifest as the drift reference |
| 1 | #16034 | Operator CLI generated from OpenAPI, over the Unix-socket listener |
| 1 | #16035 | Runtime invariant registry (6a) |
| 2 | #16031 | Per-role backup declared in the manifest |
| 2 | #16033 | Audit entries carry the on-disk delta — `blocked_by` #16032 |
| 2 | #16036 | Updates drain borrowable roles; `reboot_strategy` made live (6b) |
| 2 | #16037 | Per-node advisory exposure inventory (6c) |

Related defects, filed separately and not children: **#16025** (role shape has two sources of truth),
**#16026** (`manifest_loader` hardcoded cache TTL, no dev bypass).
