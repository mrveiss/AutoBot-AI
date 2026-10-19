# Audit and event-record systems (#17225)

Re-verified against `main` when D1/D2/D3/D5/D6 landed. Counts are call sites in non-test Python, found
by grepping the **behaviour** (a store write onto an audit-shaped key, an audit ORM row, an
`INSERT INTO ...audit`, an append to an audit path), not only the symbol names. The guard
`repo_tests/audit_writer_single_source_17225_test.py` applies the same detector to the tree and
fails on a writer outside the pinned set.

The first inventory (eight stores plus one non-store writer) was incomplete: a behaviour sweep found
five more audit stores it had missed. They are rows 9-13 below. Row 9 became the system of record
(D1, owner decision 2026-10-11). Rows 5 and 10-13 are decided and tracked separately: #18284 (rows 5
and 10), #18285 (row 11), #18286 (row 12); row 13 stays the SLM's own node-operation log.

## The canonical service

`autobot-backend/services/audit/`:

| Module | Role |
|---|---|
| `audit.py` | The one write path (`record`, `emit`, `emit_security`/`emit_compliance`/`emit_knowledge`, `audit_record`) and read path (`query`, `query_filtered`, `query_events`, `count_since`), plus `apply_retention` and `rebuild_projection`. Every producer reaches `record`, which also feeds threat detection (#13562), writes the `audit_logs` row, then the projection. |
| `store.py` | The system of record: Postgres `audit_logs`. Inserts rows, answers every query (one SQL statement per question), counts. Declares `system_of_record("audit_trail")`. |
| `taxonomy.py` | `AuditEvent`, `AuditCategory`, `AuditFilter`, and the three legacy action vocabularies (`AuditAction`, `ComplianceEventType`, `AuditEventType`). |
| `projection.py` | The Redis projection, and the only module that writes an `audit:` key: `audit:unified` plus `audit:category:<cat>`. Rebuilt from `audit_logs` by `rebuild_projection`; nothing reads it as an answer. |
| `retention.py` | The one retention policy table (D5). |
| `purge.py` | The one purge path, used by the nightly task and the admin cleanup endpoint. |
| `knowledge_view.py` | `KnowledgeAuditLog`: the knowledge audit API's views over KNOWLEDGE events. |

`autobot_shared/user_management/audit_rows.py` `audit_row` is the one constructor of an `audit_logs`
row -- used by `store.py` and by the shared RBAC, organisation and team writers, so both processes
(backend, SLM) write one schema.

"Everything recorded for user U in window W" is one call: `query(actor_id=U, from_ts=..., to_ts=...)`,
one `SELECT ... WHERE actor = U AND created_at BETWEEN ...` across every category and every writer.
`query_filtered` raises `AuditStoreUnavailable` when the store cannot be read, so an unreadable
trail is never reported as an empty one (#13258).

## Inventory

| # | Module | Store | Status | Writers | Retention | Tamper protection |
|---|---|---|---|---|---|---|
| 1 | `services/audit/` (canonical) | Postgres `audit_logs` (row 9), projected to Redis `audit:unified` + `audit:category:<cat>` | **Canonical.** `store_authority.py`: `audit_trail`, POSTGRES, projection REDIS. | All of rows 2, 3, 4, 7, 8 below, plus direct `emit`/`record` producers | Projection: `retention.py` table. Rows: not purged (see D5). | The table is append-only by convention; no trigger or revoke. |
| 2 | `services/audit/audit_log.py` | Redis `audit_log:<user>` / `audit_log:global` | **Retired (D2), module deleted.** `AuditAction` moved to `taxonomy.py`; `audit_record` is the canonical helper. | 0. Callers already used the canonical bridge: 14 `audit_record` sites in `api/chat_sessions.py` (3), `api/knowledge.py` (5), `api/secrets.py` (2), `services/device_jwt.py` (1), `services/run_jwt.py` (3) | Old keys expire by their 90-day TTL | n/a |
| 3 | `services/audit_logger.py` | Redis `audit` database (db 10): daily `audit:log:<date>` and five index zsets, JSONL fallback | **Adapter (D3).** Stores nothing; `AuditEntry` is recorded as a SECURITY `AuditEvent` and read back from #1. | `audit_log()`: 18 sites in 11 modules (`api/feature_flags.py` 2, `api/knowledge_source_liveness.py` 1, `api/mcp_external_servers.py` 1, `api/memory_privacy.py` 6, `api/scheduler_toggles.py` 2, `services/approval_execution.py` 1, `services/mcp_external_bridge.py` 1, `services/orphan_repair.py` 1, `services/orphan_storage_cleanup_action.py` 1, `services/realtime_mcp_bridge.py` 1, `scripts/migrate_shared_facts_index.py` 1); `get_audit_logger().log`: 4 (`middleware/audit_middleware.py` 3, `services/gateway/egress_governor.py` 1). Reader: `api/audit.py` (6 endpoints). | db-10 keys expire by the TTL they were written with | n/a |
| 4 | `security_layer.py` `SecurityLayer.audit_log` | JSONL file at `config.audit_log_file` | **Routed through #1 (D6).** One tamper mechanism; no second hash chain. A record that cannot be scheduled is counted (`autobot_audit_write_failures_total`, `NotScheduled`). | 64 call sites in 15 modules (`api/agent.py`, `auth_middleware.py`, `auth_rbac.py`, `worker_node.py`, ...). Readers `get_command_history` and `get_audit_entries` (`api/security.py`). | Table (SECURITY) | via #1 |
| 5 | `models/workflow_audit.py` + `services/workflow_permission_service.py` | Postgres `workflow_audit_log` | Decided: record through #1 -- #18284. | 1 | None | Convention only |
| 6 | `middleware/audit_middleware.py` | Not a store: feeds #3 | via #3 | 3 | via #1 | via #1 |
| 7 | `services/event_log.py` | Redis `autobot:event_log` | **Retired (D2), module deleted.** `ComplianceEventType` moved to `taxonomy.py`. | 0. `api/voice_bundle_admin.py` (1, the only direct writer, whose records were invisible to the admin events API) and `api/auth.py` (2) now call `emit_compliance`. | Old key expires by its 90-day TTL | n/a |
| 8 | `knowledge/audit_log.py` | Redis `audit:user:<id>`, `audit:fact:<id>`, `audit:org:<id>` + `setex` bodies | **Retired (D2), module deleted.** `knowledge_view.KnowledgeAuditLog` records and reads KNOWLEDGE events in #1; the double write is gone. | 0 (no production caller ever called `log_event`). Reader: `api/knowledge_audit.py` (5 endpoints). | Old keys expire by their TTL | n/a |
| 9 | `autobot_shared/user_management/models/audit.py` (`AuditLog`) | Postgres `audit_logs` (+ `category`, `actor`, `session_id`, `resource_ref` from #17225) | **The system of record (D1).** | All through `audit_row`: `services/audit/store.py`, `rbac_middleware.py` (denial audit, #14750), `organization_service.py`, `team_service.py`, `user_service_base.py` (the one UserService both backends use since #18267). | None | Convention only |
| 10 | `services/secrets_audit_store.py` | SQLite `secrets_audit` | Missed. Decided: record through #1 -- #18284. | 1 module | None | None |
| 11 | `a2a/trust_score.py` | SQLite `trust_audit` | Missed. Decided: a domain history table emitting GOVERNANCE events -- #18285. | 1 module | None | None |
| 12 | `security/enterprise/compliance_manager.py` | Encrypted/plain JSONL under `audit_base_path` | Missed. Decided: wire in through #1 -- #18286. `ComplianceManager` has no production constructor call (exported only). | 1 module | None | Fernet encryption for sensitive events |
| 13 | SLM backend (`autobot-slm-backend/api/security.py`, its `user_service.py`) | SLM's own `AuditLog` table | Missed. A separate service. | 2 modules | n/a | n/a |

Not stores, recorded for completeness: `workers/audit_tasks.py` keeps code-audit **daemon state**
under `audit:testgaps:*`, `audit:dead_code:*`, `audit:claims:*`, `audit:deferred_findings`,
`audit:filing_status` (D4, below). `services/terminal_websocket/audit.py` and `api/secrets.py`'s
`audit_log()` write only to the application log. `autobot-infrastructure/shared/scripts/secrets_manager.py`
keeps an `audit_log.json` outside the guard's roots.

## Decisions (owner, 2026-10-10) and status

| # | Decision | Status |
|---|---|---|
| D1 | Postgres is the system of record; Redis a projection | **Done.** Owner decision 2026-10-11: extend the existing `audit_logs` table instead of adding `audit_event`. Alembic `20261011_098` (backend) and `add_audit_logs_canonical_columns` (SLM `slm_users` database) add `category` (NOT NULL, server default `security`), `actor`, `session_id`, `resource_ref` and two indexes -- additive, no existing row rewritten. `record` writes the row, then the projection; every read is a query on the table. The guard fails on any `AuditLog(...)` outside `audit_row` (the SLM's own `slm_node_audit_logs` model excepted). |
| D2 | Retire #2, #7, #8 by repointing callers; old keys expire by TTL | **Done.** Modules deleted, callers repointed, guard forbids their import. No stored data was touched. |
| D3 | `audit_log()` becomes an adapter onto #1 | **Done.** |
| D4 | Daemon keys get their own prefix | **Not implemented: needs a data move.** `audit:deferred_findings` is a dead-letter queue with no TTL; renaming the key in code orphans every queued finding, and `audit:dead_code:last_inventory` is the diff baseline (losing it re-files every finding). The move needs a `RENAME` of the existing keys at the same moment as the code change, which is a #17038 action. The harm the shared prefix caused (the retention task trimming daemon zsets) is gone with D5: the purge no longer scans `audit:*`. |
| D5 | One retention policy table | **Done for the projection.** `retention.py` (`AUTOBOT_AUDIT_<CATEGORY>_RETENTION_DAYS`, defaults 90/90/365/365) drives the projection TTLs and the one purge path. `audit_logs` rows are not purged: the table is documented as immutable and deleting compliance records is an owner decision (#17038). `AUTOBOT_AUDIT_RETENTION_DAYS` stays the nightly purge's on-switch (0 = off) and only ever shortens a period. The old task trimmed every `audit:*` zset at one period, cutting 365-day records at 90. |
| D6 | Route `security_layer.py` through #1 | **Done.** |

## Behaviour changes a reviewer should know

* `audit.emit(AuditEvent(...))` records the event it is given. It used to be shadowed by an
  `ComplianceEventType` bridge, so 7 producers (`services/task_claim.py`, `api/voice_bundle_user.py` x2,
  the four retention tasks) recorded a COMPLIANCE event whose action was the event's repr.
* A producer on a thread with no running loop (a sync FastAPI handler, a worker thread) hands its
  record to the serving loop instead of dropping it.
* Reads scan newest-first (`zrevrangebyscore`), so a trail longer than the scan cap shows its most
  recent records, not its oldest.
* The operation-audit dashboard (`api/audit.py`) and the security-layer views now show records from
  every producer -- including the RBAC denials and org/team changes already in `audit_logs` -- for
  the same filters. Records written to the retired Redis stores before the upgrade are not shown
  (they stay in Redis until their TTL).
* Every audit record now costs one Postgres insert. If the insert fails, the projection is still
  written and the loss of the durable copy is logged and counted
  (`autobot_audit_write_failures_total`).
* `GET /api/security/audit-log` returns newest-first.

## Data-move proposal (for the #17038 approval queue; not implemented)

1. Optional backfill for visibility: copy db-10 `audit:log:<date>` entries, `audit_log:global`,
   `autobot:event_log` and the knowledge `audit:*:<id>` bodies into `audit:unified`/
   `audit:category:*` in the canonical shape, so records from before the upgrade remain visible
   until they would have expired. Without it they are retained but unreadable for up to 90/365 days.
2. D4: `RENAME audit:testgaps:last_run`, `audit:dead_code:last_inventory`, `audit:claims:last_run*`,
   `audit:deferred_findings`, `audit:filing_status` to a `daemon:audit:` prefix, deployed together
   with the matching constant change in `workers/audit_tasks.py`.
3. D1: backfill the records already in the Redis projection (`audit:unified`) into `audit_logs`, so
   the system of record starts complete. Without it, the trail before the upgrade is only in Redis.
