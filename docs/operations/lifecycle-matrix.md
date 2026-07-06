# SLM Component Lifecycle Matrix (#10016 member 1)

Single source of truth for **every component × 4 lifecycle phases** (Install · Backup · Update · Restore),
with the *verified-in-code* current procedure or the gap. Every cell cites the exact file so claims are
checkable (per the verify-in-exact-commit discipline). Last verified: 2026-07 against `Dev_new_gui`.

Legend: ✅ implemented (file cited) · ⚠️ partial (gap noted) · ❌ none.

| Component | Install | Backup | Update | Restore |
|---|---|---|---|---|
| **PostgreSQL** | ✅ `ansible/roles/postgresql` | ✅ `backup-node-data.yml` `pg_dumpall --clean --if-exists \| gzip` | ✅ code-sync + `deployment.py` migrations | ✅ `stateful.py POST /backups/{id}/restore`; `disaster-recovery.md` |
| **Redis** | ✅ `ansible/roles/redis` | ✅ `access_control/tasks/backup.yml` BGSAVE + RDB | ✅ role re-run | ✅ RDB reload; `disaster-recovery.md` Scenario 3 |
| **ChromaDB** | ✅ `ansible/roles/redis/tasks/chromadb.yml` (`/opt/autobot/autobot-db-stack/chromadb/data`) | ✅ `backup-node-data.yml` ChromaDB block (**path bug fixed #11097** — had stat'd stale `/var/lib/chromadb` → no-op) | ✅ `chromadb-1x-upgrade.md` | ⚠️ no restore step — **GAP** |
| **Backend** | ✅ `ansible/roles/backend` (python314 venv) | n/a (stateless; secrets/.env below) | ⚠️ code-sync rsync+restart; **backend `pip install` on requirements change missing → #11069** | ✅ code-cache rollback (below) |
| **SLM backend** | ✅ `ansible/roles/slm_manager` | ✅ DB (postgres) + `data/.slm_keys` | ✅ code-sync | ✅ DB restore |
| **Frontends** | ✅ `ansible/roles/frontend` | n/a (rebuilt from source) | ✅ code-sync rebuilds dist (`#9982`/#10120) | ✅ rebuild from code-cache sha |
| **Workers** (npu/tts/ai-stack/browser) | ✅ `ansible/roles/{npu-worker,tts-worker,ai-stack,browser}` | n/a (stateless) | ✅ code-sync | ✅ re-provision |
| **Secrets/config** | ✅ auto-provisioned (`service_auth`, `db-credentials.env.j2`) | ✅ `backup-node-data.yml` archives `/etc/autobot` (holds `slm-secrets.env` — master key `SLM_ENCRYPTION_KEY`) + TLS certs | n/a (`.env` rsync-excluded) | ⚠️ manual restore only — **GAP** |
| **Prometheus/monitoring** | ✅ `ansible/roles/monitoring` | ✅ `backup-node-data.yml` prometheus data | ✅ role re-run | ✅ data restore |

## Cross-cutting mechanisms (verified)

- **Backup API** — `autobot-slm-backend/api/stateful.py`: `GET /backups`, `GET /backups/{id}`, `POST /backups` (trigger), `POST /backups/{id}/restore`.
- **Update / code-sync** — `services/sync_orchestrator.py` (drift → rsync → `_restart_systemd_service`), DB-generated inventory `services/inventory_builder.py` (#9996 ✅), drift checker covers frontend source (#9982/#10120).
- **Rollback** — `services/deployment.py rollback_deployment()`, `services/blue_green.py rollback()` + `auto_rollback`/`rollback_window_seconds` (`services/database.py`), code cache `SLM_CODE_CACHE=/var/lib/slm/code-cache/<sha>`.
- **UI** — `autobot-slm-frontend/src/views/SystemUpdatesTab.vue` (update), `BackupsView.vue` (backup/restore).
- **Disaster recovery** — `docs/operations/disaster-recovery.md` (per-component failure scenarios).

## Verified gaps → remaining #10016 work

1. **Backup schedule + retention** (member 2) — `backup-node-data.yml` + API exist but no cron/timer schedule or retention/prune policy.
2. ~~ChromaDB + secrets in unified backup~~ — **RESOLVED**: ChromaDB block existed but stat'd a stale path (fixed #11097); secrets are captured via the `/etc/autobot` config archive. Both verified in-commit.
3. **Restore-verification play** (member 3) — no play that restores into a scratch target and health-checks (only in-place restore exists).
4. **Backend dep-install on update** (member 4) — code-sync doesn't `pip install` on a requirements change → **#11069** (must replicate the backend role's filtered-requirements + `-c ../constraints/shared.txt` install; delicate).

Members 5 (rollback) and 6 (UI) are implemented; members 2 (schedule/retention remainder), 3, and 4 have the scoped gaps above.
