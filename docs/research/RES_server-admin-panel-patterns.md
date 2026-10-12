# Research: Server-administration control-panel patterns

Status: Phase 1 and Phase 2 complete. Issue tree: #18494 (children #18478-#18493, #18498); related sighting added to #17658.
Date: 2026-10-12

## Source Analysis: a long-lived, open-source web control panel for Unix server administration

### What It Is
A mature (20+ years, actively committed as of 2026-10), BSD-licensed, Perl web panel for configuring a
Unix host and its services — users, firewall, DNS, mail, web servers, databases, cron, packages,
systemd, disks/RAID/LVM, and more — through a browser. Roughly 116 bundled modules plus a third-party
module ecosystem; claims about 1M yearly installs (self-reported). It ships its own HTTP server and
has a sibling "end-user subset" product and a hosting-panel product built on top of it.

### Architecture & Key Patterns
- **Plugin monolith.** One process (a self-contained Perl HTTP server, ~1.3k lines) serves CGI scripts
  from ~116 top-level module directories. A shared core library (~15k lines) gives every module the
  same primitives: config load/save, ACL lookup, i18n, file locking, action logging, UI widgets, RPC.
- **Uniform module contract.** Every module directory carries the same small set of files:
  - `module.info` — name, description, `depends=` (inter-module dependencies), OS support.
  - `config.info` — a **declarative config schema**: one line per key → label, widget type, allowed
    values. The generic "Module Config" page is rendered from it, so no module writes its own settings UI.
  - `config-<os>[-<version>]` — **per-distribution default config files** (Debian, RHEL, FreeBSD,
    Solaris, …); the installer picks the one matching the detected OS.
  - `acl_security.pl` + `defaultacl` — the module's own **per-user permission schema** and its editor.
  - `log_parser.pl` — turns the module's raw action-log records into human-readable sentences.
  - `backup_config.pl` — declares which files the module owns so a central backup module can
    snapshot/restore them.
  - `lang/` and `module.info.<locale>` — i18n per module (`.auto` suffix marks machine translation).
- **Cross-module calls** via `foreign_require(module, lib)` / `foreign_call`, and **the same calls
  across hosts** via `remote_foreign_require` / `remote_foreign_call` to an RPC endpoint on another
  instance with a session — the basis of the `cluster-*` modules (fan one action out to N servers).
- **Monitor plugins.** The status module has one `<type>-monitor.pl` per check type (load, memory,
  disk, http, dns, ftp, imap, ldap, service, process, file-change, …), each implementing three
  functions: `get_<type>_status` (returns `{up, value, desc}`), `show_<type>_dialog`,
  `parse_<type>_dialog`. Adding a check type = dropping one file.
- **Module-owned scheduled jobs** through a small cron library (`create/find/delete_<panel>_cron`,
  `delete_<panel>_module_crons`) so a module's jobs are cleaned up with the module.

### Notable Implementation Details
- **Audit log with config-file diffs and one-click rollback.** `lock_file()` snapshots a file's
  content before an edit; `<panel>_log(action, type, object, params)` then records the action *and*
  the diff of every file locked during the request. The action-log viewer shows each diff and a
  rollback page restores the selected files (incl. symlinks) — with its own ACL bit and per-user /
  per-module visibility checks. Free-text **annotations** can be attached to any logged action.
- **Action hooks.** If an action-script directory is configured, every logged action runs executables
  from `<dir>/<type>/<action>/`, `<dir>/<type>/`, `<dir>/` with `ACTION_MODULE/TYPE/OBJECT/PARAM_*`
  in the environment — a zero-code extension point for "when X is changed, do Y".
- **Read-only mode** short-circuits logging and writes globally (`is_readonly_mode`).
- **Wrapped command execution** — `system_logged` / `backquote_logged` record commands into the same
  action log, so the audit trail includes what was executed, not just what was clicked.
- **Log retention** is time-based and clears diffs/annotations together with their parent entries,
  and log rotation discards orphaned diffs.
- **Monitor results expose an SNMP MIB**, and the dashboard can show monitors per user scope.

### Strengths
- Extremely uniform module contract — new capability = new directory with known file names.
- Declarative config schema and per-OS defaults remove a whole class of per-module UI and
  per-distro branching.
- Audit trail is *actionable*: diff + rollback + annotation per action, not just a log line.
- Per-module, per-user ACLs authored by the module itself.
- Multi-host fan-out reuses the local function-call contract unchanged.
- Breadth: covers nearly every classic Unix service.

### Weaknesses / Limitations
- CGI-per-request Perl with global state (`%in`, `%text`, `%config`); synchronous, page-reload UI.
- Lock files are PID-based `.lock` files (the source itself calls them "not 100% reliable").
- Tests are thin: a handful of `.t` files for a ~116-module codebase.
- Security history is long (root-running daemon with a large CGI surface); the RPC endpoint is a
  high-value target. Many modules parse and rewrite native config files by hand.
- No structured events/streaming; status is polled by refresh or cron.
- Machine-translated locale files are mixed in alongside human ones.

### Visible vs Hidden Metrics
- **Visible:** ~6k stars, ~1M yearly installs and 116 modules (all self-reported); breadth of
  supported services and OSes; decades of production use.
- **Hidden:** the breadth is carried by hand-written parsers for dozens of native config formats per
  OS — a huge maintenance surface; the root-privileged, CGI-wide attack surface; a Perl skill
  dependency; snapshot-diff rollback is file-level only (no service restart ordering, no
  cross-file transactional guarantee, no handling of state outside files).
- **Weighing:** adopting the *product* would import all hidden costs for little gain. The
  *patterns* — declarative config schema, per-module manifest contract, diff-capturing audit log with
  rollback, monitor-plugin triple, action hooks — are cheap to borrow and carry none of the
  maintenance burden, since they are conventions rather than code.

---

## AutoBot Comparison (Phase 2) — scoped to log handling, monitoring, updates, system configuration

Scope rule (owner, 2026-10-12): compare only areas AutoBot already has; **do not build a second
control panel**. Every item below improves an existing AutoBot feature. Audits ran against
`origin/main` at `df211d3ba6`; items marked ✔ were re-verified by direct read.

### Defects found during the audit (fix regardless of adoption)

| # | Defect | Evidence |
|---|---|---|
| D1 ✔ | Config rollback records a new revision row but never re-applies the config to the live store | `autobot-backend/services/config_revision_service.py` `rollback_to_revision` — only calls `create_revision` |
| D2 | Config-revision list/rollback routes require only login; route `entity_type/entity_id` not checked against the revision | `autobot-backend/api/config_revisions.py:63,90,127` |
| D3 ✔ | Default `AUTOBOT_AUDIT_RETENTION_DAYS=0` ("disabled") is passed straight to `EXPIRE key 0`, which deletes the daily audit sets on write — unless the env var is set on the host (host value not checked) | `autobot_shared/ssot_config.py` `audit_retention_days`; `autobot-backend/services/audit_logger.py:494-500` |
| D4 ✔ | `AlertRule` CRUD + UI exist but no evaluator reads the rules — dead config | only reference outside the model is `autobot-slm-backend/api/performance.py` |
| D5 ✔ | Update routes fetch the user and discard it (`_`); updates write no audit record | `autobot-slm-backend/api/updates.py:605…1078`, `api/code_sync.py:3291` |
| D6 | `access_control` role references a missing `audit_logrotate.j2` | `ansible/roles/access_control/tasks/audit_logging.yml:26` |
| D7 | Config YAML opened with `"w"` (truncate) before `flock` is taken | `autobot-backend/services/config_service.py:596-605` |
| D8 | Agent publishes service state changes to Redis with no production subscriber; Prometheus `alertmanagers: []` so alert rules fire nowhere | `slm/agent/health_collector.py:411`; `prometheus.yml.j2:13` |

### What We Can Adopt

| Pattern from the reference work | AutoBot target | Audit (exists?) | Visible benefit / hidden cost | Verdict | Effort |
|---|---|---|---|---|---|
| **Audit entry carries the change diff + rollback from the log** | backend `audit_logger` ↔ `config_revisions`; SLM `AuditLog` | Partial — revisions hold before/after but are a separate store; audit entries carry no revision link; rollback broken (D1) | One trail answers "who changed what, and undo it" / adds a FK + rollback must actually call the config writer per entity type | **Adopt** — fix D1, link `revision_id` into audit `details` | moderate |
| **Every privileged action audited, incl. executed commands** | SLM `create_audit_log` from `code_sync`, `updates`, `services`, `nodes_execution`; backend `security_layer` JSONL → `AuditLogger` | Partial — SLM audit used only by auth/SSO; commands go to 3 separate sinks | Single source for compliance / one shared helper, risk of audit volume | **Adopt** | moderate |
| **Annotations on audit entries** | backend `AuditEntry`, SLM `AuditLog`, viewers | Absent | Incident context next to the event / schema + UI field | Adopt-with-conditions — after the two above | trivial |
| **Monitor-plugin contract** (`status()` → `{up,value,desc}`; one file per check type) | `slm/agent/health_collector.py` fixed methods; reconciler checks | Absent — hardcoded methods, TTS-only HTTP probe dict | New check = one file; enables user-defined monitors / refactor of a byte-duplicated agent copy | **Adopt** — registry inside the existing collector, not a new subsystem | moderate |
| **Alert rules evaluated + notify-on-change with dedup** | wire existing `AlertRule` (D4) into reconciler; reuse `alert_cooldown` | Rules stored, never evaluated; change-only dedup exists for status | Makes an already-shipped UI real / evaluator loop + notification channel delivery | **Adopt** (completes unwired work, not new) | moderate |
| **Scheduled OS updates with modes** (notify-only / security-only / all) + pre/post gate scripts | `api/updates.py`, `schedule_executor.py`, `apply-system-updates.yml` | Playbook supports `update_type=security`; API never sends it; no OS-update schedule; `update-policy` readable but never applied | Closes a real fleet gap using existing playbook / must reconcile with `unattended-upgrades` already enabled by `deploy-base.yml` | **Adopt** | moderate |
| **Detect OS auto-update services that conflict with managed updates** | same | Absent | Avoids two updaters racing apt locks / small | Adopt (part of previous) | trivial |
| **Reboot-required surfaced** (`/var/run/reboot-required`, `needrestart`) | `UpdateJob` model + `SystemUpdatesTab.vue` | Playbook detects it; API hardcodes `auto_reboot=false`; result never stored/shown | Operator knows a node is pending reboot / one column + badge | **Adopt** | trivial |
| **Package holds** (pin a package against updates) | `api/updates.py` | Not found (searched `hold|apt-mark` in updates API) | Protects pinned deps (e.g. GPU drivers) / apt-mark wrapper | Adopt-with-conditions — only if a held-package need is confirmed | moderate |
| **Log-viewer context lines + compressed rotated logs** | `autobot-backend/api/logs.py`, SLM `LogViewer.vue` | Absent (client-side search only, rotated `.gz` not searched) | Search survives rotation / server-side grep | Adopt-with-conditions | moderate |
| **Journal unit allowlist / role gate** | SLM `api/services.py:581` journal route | Router gated by `require_service_management` (`main.py:672`), but any unit readable — format check only, no allowlist (#18492) | Least privilege on node logs / allowlist from `Service` rows | **Adopt** | trivial |
| **Optimistic concurrency on config edits** (version/etag) | backend `settings_config`, SLM `api/settings.py` | Absent — last writer wins | No silent overwrite between two admins / `If-Match` on 2 APIs | Adopt | moderate |

### Rejected by hidden metrics

| Pattern | Why rejected |
|---|---|
| Declarative settings schema generating **all** settings pages | AutoBot already has `SchemaForm.vue` (plugins) and pydantic SSOT; migrating ~41 hand-written settings views is a large rewrite with UX regression risk for little user-visible gain. Use `SchemaForm` for *new* simple pages only. |
| Per-OS default config files | Fleet is Debian/Ubuntu-only by design (enrollment rejects others); adds matrix cost with no consumer. |
| Same-contract remote function calls (RPC to remote instance) | AutoBot uses agent heartbeat + Ansible/SSH; an RPC endpoint on every node adds a root-level attack surface. |
| Filesystem action-hook directory (`<dir>/<type>/<action>/`) | AutoBot already has `trigger_service` (webhook/cron/pubsub/agent-event); an exec-dir hook bypasses the egress/approval model. Instead: let audit events be a trigger source. |
| Global read-only mode | No requested use case; touches every write path. |
| SNMP export | Prometheus already exported; SNMP adds a protocol nobody consumes. |

### What We Already Do Better

- **Self-update:** detached Ansible run survives restart, resume plan, fail-closed `pg_dump` before
  migrations, log-reader verdict after restart, deployed-commit verification, rolling fleet sync with
  batch size and SLM-last ordering. The reference work's update is a per-host package upgrade.
- **Log viewer safety:** path containment (`require_contained_relative_path`), protected files,
  admin-only, WebSocket follow, container logs, outbound forwarding (syslog/Loki/ES/webhook).
- **Monitoring transport:** push heartbeat with offline SQLite buffering, Prometheus + Grafana +
  node_exporter, WebSocket live fleet view, auto-remediation with cooldown/max-attempts.
- **Secret-aware config history:** revisions redact secrets before storing diffs.

### Gaps & Opportunities (priority)

1. **Fix defects D1, D3, D5, D2** — data loss / broken rollback / missing audit on the most privileged actions.
2. **Wire `AlertRule` evaluation + a notification path** (D4, D8) — completes shipped-but-dead UI.
3. **OS update modes + schedule + reboot-required surfacing** — reuse existing playbook flags.
4. **Monitor check registry** inside `health_collector` — unlocks configurable checks.
5. **Audit ↔ revision link, annotations, unified command audit sink.**
6. **Config optimistic concurrency (#18493); journal unit allowlist (#18492); SLM settings history (#18498).**

### Specific Code/Files Affected

- `autobot-backend/services/config_revision_service.py`, `api/config_revisions.py` — apply on rollback, admin gate, entity check.
- `autobot-backend/services/audit_logger.py` — skip `EXPIRE` when retention ≤ 0.
- `autobot-backend/services/config_service.py` — lock before truncate; version field.
- `autobot-backend/security_layer.py` — route command audit into `AuditLogger`.
- `autobot-slm-backend/api/updates.py`, `api/code_sync.py`, `api/services.py`, `api/nodes_execution.py` — `create_audit_log` with user; `update_type=security`; reboot flag.
- `autobot-slm-backend/models/database.py` — `UpdateJob.reboot_required`, `UpdateJob.user`; `AuditLog.annotation`.
- `autobot-slm-backend/services/reconciler.py` — `AlertRule` evaluator; `services/schedule_executor.py` — OS-update schedules.
- `autobot-slm-backend/slm/agent/health_collector.py` (+ ansible copy) — check-type registry.
- `autobot-slm-backend/ansible/roles/access_control/` — missing logrotate template.
- `autobot-slm-frontend/src/views/SystemUpdatesTab.vue`, `views/monitoring/LogViewer.vue` — reboot badge, security-only action.
