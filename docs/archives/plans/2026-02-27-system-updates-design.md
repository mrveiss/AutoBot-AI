# System Updates — Real Package Discovery & Badge Indicators

**Date:** 2026-02-27
**Status:** Approved
**Related Issues:** #840, #1230, #682

## Problem

The System Updates tab currently reads from a pre-populated `UpdateInfo` database table but has no mechanism to actually discover available system packages via `apt update` + `apt list --upgradable`. The sidebar badge only reflects Code Sync outdated nodes — system package updates are invisible.

## Goals

1. Add real package discovery via Ansible playbook on fleet nodes
2. Show combined update indicators in sidebar badge
3. Show per-tab badges (system updates count + code sync outdated count)
4. Support both "upgrade all" and "select specific packages" workflows
5. Allow filtering by node or role

## Architecture

### Approach: Ansible-Only Pipeline

All interactions with fleet nodes go through Ansible playbooks — consistent with the existing `apply-system-updates.yml` pattern.

```
User clicks "Check for Updates"
  → POST /api/updates/check { node_ids?, role?, scope }
  → Backend creates check job (DB record)
  → Background task runs Ansible: check-system-updates.yml
  → Ansible: apt update + apt list --upgradable on each node
  → Ansible writes structured JSON output per host
  → Backend parses output, upserts UpdateInfo records (dedup by node+package)
  → WebSocket broadcasts progress
  → Frontend polls job status → shows results when complete
```

## Backend Changes

### New Ansible Playbook: `check-system-updates.yml`

Targets selected nodes. Runs:
1. `apt update` (refresh cache)
2. `apt list --upgradable` (discover packages)
3. Outputs structured JSON per host: package_name, current_version, available_version, severity (security vs regular), source repository

Output written to `/tmp/system-updates-check-<job_id>.json` on the Ansible control node.

### New/Modified API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `POST /api/updates/check` | POST | Trigger package discovery. Accepts `node_ids`, `role`, `scope` (all/role/specific). Creates async check job. |
| `GET /api/updates/check-status/{job_id}` | GET | Poll check job progress |
| `GET /api/updates/packages` | GET | List discovered upgradable packages from DB. Filter by `node_id`, `severity`. |
| `GET /api/updates/summary` | GET | Lightweight count endpoint for badge display. Returns `{ system_updates: N, last_checked: timestamp }` |
| `POST /api/updates/apply` | POST | Existing — enhanced to support `upgrade_all: true` mode alongside specific packages |

### Database

Existing `UpdateInfo` model is reused. New field: `node_id` (already exists but needs to be consistently populated per-node). Dedup key: `(node_id, package_name)`.

## Frontend Changes

### SystemUpdatesTab.vue — Redesigned Layout

1. **Action Bar** — "Check for Updates" button, node/role filter dropdown, "Upgrade All" button
2. **Check Progress** — Progress bar when check job running, per-node status
3. **Summary Stats Cards** — Total upgradable, Nodes needing updates, Security updates, Last checked
4. **Available Packages Table** — Grouped by node. Columns: Checkbox, Package Name, Current → Available Version, Severity badge, Node. Multi-select + "Upgrade Selected" button.
5. **Upgrade Jobs Table** — Existing job tracking (running/completed/failed)

### Sidebar Badge (Combined)

- New composable: `useSystemUpdates()` — polls `GET /api/updates/summary` every 60s
- Sidebar badge shows combined count: `systemUpdateCount + codeSyncOutdatedCount`
- Badge color: amber when only code sync, orange/red when system updates present

### Tab Badges

- System Updates tab: orange badge with upgradable package count
- Code Sync tab: existing amber badge for outdated nodes (unchanged)

### UpdatesView.vue

- Import `useSystemUpdates()` composable
- Add badge to System Updates tab showing package count

## Webmin Reference Patterns Applied

1. **Cache management**: Store last check timestamp, don't re-check if within TTL
2. **Simulation before execution**: Dry-run mode via Ansible `check_mode: true`
3. **Non-interactive execution**: `apt-get -y` with `DEBIAN_FRONTEND=noninteractive`
4. **Security classification**: Parse source repository to tag security vs regular updates
5. **Held package filtering**: Skip packages marked as held via `apt-mark showhold`

## File Changes Summary

### New Files
- `autobot-slm-backend/ansible/check-system-updates.yml` — Package discovery playbook
- `autobot-slm-frontend/src/composables/useSystemUpdates.ts` — System updates composable

### Modified Files
- `autobot-slm-backend/api/updates.py` — New endpoints (POST check, summary, packages)
- `autobot-slm-frontend/src/views/SystemUpdatesTab.vue` — Redesigned with package table + actions
- `autobot-slm-frontend/src/views/UpdatesView.vue` — Add system updates tab badge
- `autobot-slm-frontend/src/components/common/Sidebar.vue` — Combined badge (system + code sync)
