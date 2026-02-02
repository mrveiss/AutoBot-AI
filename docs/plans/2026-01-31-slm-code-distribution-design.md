# SLM Agent Code Distribution & Version Tracking

**Date:** 2026-01-31
**Status:** Design Complete
**GitHub Issue:** TBD

---

## Overview

Implement a code distribution and version tracking system for SLM agents running across the fleet. The SLM machine pulls from GitHub and distributes code to agents, with GUI notifications when nodes need updates.

## Key Decisions

| Decision | Choice |
|----------|--------|
| Version tracking | Git commit hash |
| Distribution model | Hybrid (notify via heartbeat, agents pull from SLM) |
| Update triggers | Manual approval + scheduled windows |
| Service restarts | All options (auto, manual, configurable, rolling) |
| GUI notifications | All levels (badge, dedicated page, top-bar) |
| Upstream tracking | Periodic git fetch (every 5 minutes) |

---

## Architecture

### 1. Version Tracking

**Agent-side:**
- Agent embeds git commit hash at deployment time (written to `/var/lib/slm-agent/version.json`)
- Heartbeat payload includes `code_version` (commit hash) alongside existing `agent_version`
- Agent stores path to its code directory for sync operations

**SLM Server-side:**
- Background task `GitVersionTracker` fetches from GitHub every 5 minutes
- Stores latest commit hash in database/Redis
- Compares each node's reported `code_version` against latest
- Marks nodes as `up_to_date`, `outdated`, or `unknown`

**Database additions:**
- `Node` model gets `code_version: str` and `code_status: str` fields
- New `SystemSetting` for `slm_agent_latest_commit`

### 2. Hybrid Code Distribution

**Heartbeat Response Enhancement:**
```python
# SLM returns in heartbeat response:
{
  "status": "ok",
  "update_available": true,
  "latest_version": "abc123def",
  "update_url": "/api/nodes/{id}/code-package"
}
```

**Agent Update Flow:**
1. Agent receives heartbeat response with `update_available: true`
2. Agent sets internal flag `pending_update = true`
3. Agent waits for sync command (via separate API call from SLM)
4. On sync command: Agent downloads code package from `update_url`
5. Agent extracts to staging directory, validates, swaps atomically
6. Agent restarts itself (or waits for manual restart based on config)

**SLM Code Package Endpoint:**
- `GET /api/nodes/{node_id}/code-package` - Returns tarball of agent code
- SLM builds tarball from its local git checkout (already fetched)
- Includes `version.json` with commit hash baked in

### 3. Update Triggers & Restart Strategies

**Manual Sync (GUI-triggered):**
- Operator clicks "Sync" on node → API call `POST /api/nodes/{node_id}/sync`
- Options in modal:
  - ☑️ Restart service after sync (default: checked)
  - Select restart type: `immediate` | `graceful` (wait for current tasks)

**Scheduled Updates:**
- New entity: `UpdateSchedule` with cron expression, target nodes/roles
- Scheduler checks every minute, triggers sync for matching nodes
- Respects existing maintenance windows
- Logs all scheduled syncs for audit trail

**Restart Strategies:**

| Strategy | Behavior |
|----------|----------|
| `immediate` | Stop service, swap code, start service |
| `graceful` | Signal agent to finish current work, then restart |
| `manual` | Sync code only, operator restarts later |
| `rolling` | For bulk ops: sync/restart one node at a time, health check between each |

**Rolling Restart for Fleet:**
- `POST /api/fleet/sync` with `strategy: rolling`
- Configurable: `batch_size`, `health_check_delay`, `abort_on_failure`

### 4. GUI Notifications

**Node List Badge:**
- Icon overlay on nodes table
- States: 🟢 Up to date | 🟡 Update available | ⚪ Unknown
- Tooltip shows version diff

**Top-bar Notification:**
- Bell icon shows count: "3 nodes need updates"
- Dropdown lists affected nodes with quick-sync buttons

**Dedicated Updates Page (`/updates`):**

| Section | Content |
|---------|---------|
| Status Banner | Latest version, fetch timestamp, manual refresh button |
| Pending Updates | Table of outdated nodes with checkboxes |
| Bulk Actions | "Sync Selected" / "Sync All" with restart strategy |
| Schedules | Configured update schedules (CRUD) |
| History | Recent sync operations with status |

**WebSocket Integration:**
- Real-time updates when nodes report new versions
- Live progress during sync operations
- Toast notifications on sync complete/failed

---

## Implementation Components

### Backend (slm-server)

| File | Purpose |
|------|---------|
| `services/git_tracker.py` | Background task fetching from GitHub, storing latest commit |
| `services/code_distributor.py` | Builds code packages, handles sync orchestration |
| `api/updates.py` | REST endpoints for update operations |
| `models/database.py` | Add `UpdateSchedule`, extend `Node` with code_version fields |
| `models/schemas.py` | Request/response schemas for update operations |

### Agent (src/slm/agent)

| File | Purpose |
|------|---------|
| `updater.py` | Downloads package, validates, performs atomic swap |
| `agent.py` | Extended heartbeat handling, responds to sync commands |
| `version.py` | Reads/writes `version.json`, reports current commit |

### Frontend (slm-server/frontend)

| File | Purpose |
|------|---------|
| `views/UpdatesView.vue` | Dedicated updates management page |
| `components/UpdateBadge.vue` | Node status badge component |
| `components/UpdateNotification.vue` | Top-bar notification dropdown |
| `composables/useUpdates.ts` | API integration, WebSocket subscriptions |

### Ansible

- Update `slm_agent` role to embed commit hash at deploy time
- Add `version.json` template with `{{ git_commit }}` variable

---

## API Endpoints

### New REST Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/updates/status` | Latest version, fetch timestamp, outdated node count |
| `POST` | `/api/updates/refresh` | Trigger manual git fetch |
| `GET` | `/api/updates/pending` | List all nodes needing updates |
| `POST` | `/api/nodes/{id}/sync` | Sync code to specific node |
| `POST` | `/api/fleet/sync` | Bulk sync with strategy options |
| `GET` | `/api/updates/schedules` | List update schedules |
| `POST` | `/api/updates/schedules` | Create schedule |
| `DELETE` | `/api/updates/schedules/{id}` | Delete schedule |
| `GET` | `/api/updates/history` | Sync operation history |

### Heartbeat Enhancement

```python
# POST /api/nodes/{node_id}/heartbeat - Request adds:
{ "code_version": "abc123def456" }

# Response adds:
{ "update_available": true, "latest_version": "def789..." }
```

### WebSocket Events

- `node.code_status_changed` - Node version updated
- `sync.started` / `sync.progress` / `sync.completed` / `sync.failed`
- `fleet.sync.progress` - Rolling update progress

---

## Security Considerations

- Code packages are served only to authenticated agents (existing auth)
- Packages include SHA256 checksum for validation before extraction
- Atomic swap prevents partial deployments
- Rollback capability: keep previous version for quick revert

---

## Implementation Order

1. **Phase 1: Version Tracking** - Agent reports commit, SLM compares
2. **Phase 2: Git Tracker** - Background fetch from GitHub
3. **Phase 3: Code Distribution** - Package building and sync API
4. **Phase 4: Agent Updater** - Download, validate, swap logic
5. **Phase 5: GUI Updates Page** - Dedicated management view
6. **Phase 6: Notifications** - Badges and top-bar alerts
7. **Phase 7: Schedules** - Scheduled update support
8. **Phase 8: Rolling Updates** - Fleet-wide with health checks
