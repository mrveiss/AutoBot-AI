# Role-Based Code Sync Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement centralized, role-based code distribution across all AutoBot systems with a single git-connected source node, SLM as central orchestrator, and per-role version tracking.

**GitHub Issue:** TBD (create before implementation)

**Date:** 2026-02-03

---

## Architecture Overview

### Hub-and-Spoke Code Distribution

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     CODE-SOURCE NODE (role: code-version-watcher)        │
│                              172.16.168.20                                │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │ • Git repository (only git-connected node)                         │  │
│  │ • Post-commit hook notifies SLM of new versions                    │  │
│  │ • Serves code to SLM on request                                    │  │
│  │ • Role assignable to any node via SLM UI                           │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │ 1. Notify (git hook)
                                  │ 2. SLM pulls code
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                          SLM SERVER (172.16.168.19)                      │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │ CODE CACHE         │ VERSION REGISTRY    │ ROLE REGISTRY           │  │
│  │ /var/lib/slm/code/ │ tracks all node     │ role→paths mapping      │  │
│  │ cached by commit   │ versions & status   │ role→restart behavior   │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │ SYNC ORCHESTRATOR                                                  │  │
│  │ • Receives version notifications from code-source                  │  │
│  │ • Pulls code from source, caches locally                          │  │
│  │ • Distributes to nodes based on their roles                       │  │
│  │ • Integrates with existing UpdateSchedule system                  │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │ 3. Admin triggers sync
                                  │ 4. SLM pushes to nodes
                    ┌─────────────┴─────────────┬──────────────┐
                    ▼                           ▼              ▼
              [Frontend .21]             [NPU .22]      [Browser .25]
              roles: frontend,           roles: npu-    roles: browser-
              slm-agent                  worker         service
```

### Key Principles

- Single source of truth (one git-connected node)
- SLM caches code locally before distribution (resilient)
- Role-based targeting (not just node-based)
- Admin approval required for deployment (git hook only notifies)

---

## Role System

### Role Registry

| Role         | Sync Type   | Source Paths                 | Target Path                  |
|--------------|-------------|------------------------------|------------------------------|
| code-source  | -           | (git origin)                 | -                            |
| backend      | component   | backend/, src/               | /home/autobot/AutoBot        |
| frontend     | component   | autobot-vue/                 | /home/autobot/autobot-vue    |
| slm-server   | component   | slm-server/, slm-admin/      | /home/autobot/AutoBot        |
| slm-agent    | component   | src/slm/agent/               | /opt/slm-agent               |
| npu-worker   | package     | resources/windows-npu-worker | C:\AutoBot\npu               |
| browser-svc  | component   | browser-service/             | /home/autobot/browser        |

### Role Configuration Schema

```python
class RoleConfig:
    role_name: str              # e.g., "frontend"
    sync_type: str              # "component" | "package"
    source_paths: list[str]     # directories to sync from source
    target_path: str            # where to deploy on target node
    systemd_service: str | None # service to restart
    auto_restart: bool          # default restart behavior
    health_check_port: int | None
    health_check_path: str | None
    pre_sync_cmd: str | None    # run before sync
    post_sync_cmd: str | None   # run after sync
```

### Node-Role Assignment

- **assigned_roles**: Admin-assigned roles via UI
- **detected_roles**: Auto-discovered from path + service + port
- **effective_roles**: Computed (assigned overrides detected)
- **role_versions**: Per-role version tracking `{"frontend": "cd84b085"}`

### Auto-Discovery Logic

```
path + service + port  → ACTIVE
path + service         → ACTIVE
path only              → INACTIVE
nothing                → NOT_INSTALLED
```

---

## SLM Agent Enhancements

### Enhanced Heartbeat

```python
{
    "cpu_percent": 25.0,
    "memory_percent": 50.0,
    "role_report": {
        "frontend": {
            "path_exists": true,
            "service_running": true,
            "ports": [5173],
            "version": "cd84b085"
        }
    },
    "listening_ports": [
        {"port": 5173, "process": "node", "pid": 1234}
    ]
}
```

---

## Code Sync Workflow

1. **PULL**: SLM pulls code from source → `/var/lib/slm/code-cache/{commit}/`
2. **DISTRIBUTE**: Rsync role paths to target nodes
3. **RESTART**: Based on role config (auto_restart setting)
4. **UPDATE**: Mark node versions in database

---

## Database Schema

### New Tables

- **roles**: Role definitions (name, paths, restart config)
- **node_roles**: Node-role assignments with version tracking
- **code_sources**: Code source node configuration
- **sync_jobs**: Sync job history

### Modified Tables

- **nodes**: Add detected_roles, listening_ports, role_versions
- **update_schedules**: Add target_roles for role-based scheduling

---

## API Endpoints

### New

- `GET/POST /api/roles` - Role CRUD
- `GET /api/roles/definitions` - For agents
- `POST /api/code-source/notify` - Git hook
- `POST /api/code-sync/pull` - Pull to cache
- `POST /api/code-sync/roles/{role}/sync` - Sync by role
- `GET/PUT /api/nodes/{id}/roles` - Node role management

---

## Implementation Files

### New Files

```
slm-server/api/roles.py
slm-server/api/code_source.py
slm-server/services/role_registry.py
slm-server/services/code_source_manager.py
slm-server/services/sync_orchestrator.py
src/slm/agent/role_detector.py
src/slm/agent/port_scanner.py
slm-admin/src/views/CodeSyncView.vue
slm-admin/src/components/RoleManagementModal.vue
slm-admin/src/composables/useRoles.ts
```

### Modify

```
slm-server/api/code_sync.py
slm-server/api/nodes.py
slm-server/models/database.py
src/slm/agent/agent.py
slm-admin/src/composables/useCodeSync.ts
```

---

## Default Roles

| Role | Auto-Restart | Reason |
|------|--------------|--------|
| slm-agent | Yes | Lightweight |
| frontend | Yes | Stateless |
| backend | No | Active requests |
| npu-worker | No | GPU tasks |
| slm-server | No | Critical |
| browser-svc | Yes | Stateless |

---

## Summary

| Aspect | Decision |
|--------|----------|
| Architecture | Hub-and-spoke: Source → SLM → Fleet |
| Role System | DB + UI with auto-discovery + override |
| Sync Type | Hybrid: component (Linux), package (Windows) |
| Detection | Path + Service + Port |
| Triggers | Git hook notifies, Admin initiates |
| Restarts | Per-role defaults + schedules |
