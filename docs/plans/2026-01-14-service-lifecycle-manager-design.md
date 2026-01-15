# Service Lifecycle Manager (SLM) Design

> **Status**: Draft
> **Created**: 2026-01-14
> **Issue**: TBD

## Overview

Service Lifecycle Manager (SLM) is a dedicated admin machine that orchestrates the full lifecycle of AutoBot's distributed VM fleet, providing:

- Self-healing with automatic service restart
- Unified state machine for node/service states
- Proactive monitoring with automatic remediation
- Blue-green deployments with role borrowing

## Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Admin Machine (new VM)                     │
│                     172.16.168.10                            │
│  ┌─────────────────────────────────────────────────────┐    │
│  │         Service Lifecycle Manager (SLM)             │    │
│  │  - FastAPI backend (admin-only)                     │    │
│  │  - Vue admin UI (separate from AutoBot UI)          │    │
│  │  - SQLite state database                            │    │
│  │  - PKI Certificate Authority (CA root)              │    │
│  │  - Ansible controller                               │    │
│  │  - Health monitor / reconciler                      │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────┬───────────────────────────────────┘
                          │ SSH + mTLS
        ┌────────┬────────┼────────┬────────┬────────┐
        ▼        ▼        ▼        ▼        ▼        ▼
   ┌────────┐┌────────┐┌────────┐┌────────┐┌────────┐┌────────┐
   │ Main   ││Frontend││  NPU   ││ Redis  ││AI Stack││Browser │
   │ Host   ││        ││ Worker ││        ││        ││        │
   │  .20   ││  .21   ││  .22   ││  .23   ││  .24   ││  .25   │
   └────────┘└────────┘└────────┘└────────┘└────────┘└────────┘
```

### Runtime vs Management Separation

**Management Plane** (Admin Machine - can be off):
- Controls: Deployments, Updates, Role Changes, Enrollment
- When off: Fleet continues, changes queued until online

**Runtime Plane** (Always runs independently):
- Services discover each other directly (not via admin)
- Systemd ensures services auto-start on boot
- mTLS certs are pre-deployed, don't need admin to validate
- Admin machine is only needed for **changes**, not **operations**

| Action | Admin Online | Admin Offline |
|--------|--------------|---------------|
| Normal service operation | ✅ Works | ✅ Works |
| Service auto-restart on crash | ✅ Works | ✅ Works (systemd) |
| VM reboot recovery | ✅ Works | ✅ Works (systemd) |
| New deployments | ✅ Works | ❌ Waits for admin |
| Rolling updates | ✅ Works | ❌ Waits for admin |
| Role changes | ✅ Works | ❌ Waits for admin |
| Certificate renewal | ✅ Works | ⚠️ Works if not expired |

## Node State Machine

### States

```
                    ┌──────────────┐
                    │   UNKNOWN    │ (initial)
                    └──────┬───────┘
                           │ discover/add
                           ▼
                    ┌──────────────┐
         ┌─────────│   PENDING    │
         │         └──────┬───────┘
         │                │ enroll
         │                ▼
         │         ┌──────────────┐
         │    ┌────│  ENROLLING   │────┐
         │    │    └──────────────┘    │
         │    │ success              fail
         │    ▼                        ▼
         │  ┌──────────────┐    ┌──────────────┐
         │  │    ONLINE    │◄───│    ERROR     │
         │  └──────┬───────┘    └──────────────┘
         │         │                   ▲
         │    health fail              │
         │         ▼                   │
         │  ┌──────────────┐           │
         │  │   DEGRADED   ├───────────┘
         │  └──────┬───────┘    remediation fail
         │         │
         │    remediation success
         │         │
         │         ▼
         │  ┌──────────────┐
         │  │    ONLINE    │
         │  └──────────────┘
         │
         │  ┌──────────────┐
         └──│ MAINTENANCE  │ (during updates/role change)
            └──────────────┘
```

### State Definitions

| State | Meaning | Auto-Remediation |
|-------|---------|------------------|
| UNKNOWN | Just discovered, no info | None |
| PENDING | Added, awaiting enrollment | None |
| ENROLLING | Ansible running | None |
| ONLINE | Healthy, all services up | N/A |
| DEGRADED | Health check failing | Restart services |
| ERROR | Remediation failed | Alert, wait for human |
| MAINTENANCE | Planned update/role change | None |

### Maintenance Modes

```
                         ┌──────────────┐
                         │    ONLINE    │
                         └──────┬───────┘
                                │
          ┌─────────────────────┼─────────────────────┐
          │                     │                     │
          ▼                     ▼                     ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│   MAINTENANCE    │  │   MAINTENANCE    │  │   MAINTENANCE    │
│    _DRAINING     │  │    _PLANNED      │  │   _IMMEDIATE     │
│                  │  │                  │  │                  │
│ - Stop new work  │  │ - Scheduled time │  │ - Stop now       │
│ - Finish current │  │ - Graceful stop  │  │ - Force stop     │
│ - Then offline   │  │ - Then offline   │  │ - Offline        │
└────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘
         │                     │                     │
         └─────────────────────┼─────────────────────┘
                               ▼
                      ┌──────────────────┐
                      │   MAINTENANCE    │
                      │    _OFFLINE      │
                      └────────┬─────────┘
                               │
                               ▼ complete
                      ┌──────────────────┐
                      │   MAINTENANCE    │
                      │   _RECOVERING    │
                      └────────┬─────────┘
                               │
                    success    │    fail
                  ┌────────────┴────────────┐
                  ▼                         ▼
           ┌──────────────┐          ┌──────────────┐
           │    ONLINE    │          │    ERROR     │
           └──────────────┘          └──────────────┘
```

| Type | Trigger | Behavior | Use Case |
|------|---------|----------|----------|
| DRAINING | API call | Stop accepting work → finish in-flight → offline | Rolling updates |
| PLANNED | Scheduled | Wait for window → graceful stop → offline | Hardware, major upgrades |
| IMMEDIATE | API call | Force stop → offline | Emergency, security |

## Database Schema

```sql
-- Core node registry
CREATE TABLE nodes (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    ip_address      TEXT NOT NULL UNIQUE,
    ssh_port        INTEGER DEFAULT 22,
    ssh_user        TEXT DEFAULT 'autobot',

    -- State
    state           TEXT NOT NULL DEFAULT 'unknown',
    state_changed   DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- Role management
    current_role    TEXT,
    primary_role    TEXT,           -- Original role (for role borrowing)
    capability_tags TEXT,           -- JSON array: ["can_be_redis", "has_gpu"]

    -- Maintenance
    maintenance_type   TEXT,        -- draining, planned, immediate
    maintenance_reason TEXT,
    maintenance_start  DATETIME,
    maintenance_end    DATETIME,
    drain_timeout_sec  INTEGER DEFAULT 300,

    -- Health
    last_heartbeat  DATETIME,
    last_health     TEXT,           -- JSON health snapshot
    consecutive_failures INTEGER DEFAULT 0,

    -- Metadata
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Role definitions
CREATE TABLE roles (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT,
    service_type    TEXT DEFAULT 'stateless',  -- 'stateless' or 'stateful'
    services        TEXT,           -- JSON array: ["redis-stack-server"]
    required_tags   TEXT,           -- JSON array: ["has_ssd"]
    dependencies    TEXT,           -- JSON array: ["redis"]
    update_strategies TEXT,         -- JSON array: ["blue_green_swap", "maintenance_window"]
    replication_config TEXT,        -- JSON: {"method": "redis_replica", ...}
    health_checks   TEXT,           -- JSON array of check definitions
    install_playbook TEXT,
    purge_playbook  TEXT
);

-- State transition audit log
CREATE TABLE state_transitions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id         TEXT NOT NULL REFERENCES nodes(id),
    from_state      TEXT,
    to_state        TEXT NOT NULL,
    trigger         TEXT,           -- 'health_check', 'api', 'remediation', 'timeout'
    details         TEXT,           -- JSON context
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Deployment tracking
CREATE TABLE deployments (
    id              TEXT PRIMARY KEY,
    deployment_type TEXT NOT NULL,  -- 'update', 'role_change', 'enrollment'
    strategy        TEXT NOT NULL,  -- 'sequential', 'blue_green', 'replicated_swap', 'maintenance_window'
    strategy_params TEXT,           -- JSON: {"backup_before": true, "sync_timeout": 600}
    state           TEXT NOT NULL,  -- 'pending', 'running', 'completed', 'failed', 'rolled_back'
    target_nodes    TEXT,           -- JSON array of node IDs
    current_node    TEXT,
    progress        TEXT,           -- JSON progress details
    started_at      DATETIME,
    completed_at    DATETIME,
    rollback_at     DATETIME,
    error           TEXT
);

-- Scheduled maintenance windows
CREATE TABLE maintenance_windows (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id         TEXT NOT NULL REFERENCES nodes(id),
    maintenance_type TEXT NOT NULL,
    reason          TEXT,
    scheduled_start DATETIME NOT NULL,
    scheduled_end   DATETIME,
    executed        BOOLEAN DEFAULT FALSE,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## API Specification

### REST Endpoints

```
Base URL: https://admin.autobot.local:8443/api/v1

── Nodes ──────────────────────────────────────────────────────
GET    /nodes                     List all nodes with state
POST   /nodes                     Add new node
GET    /nodes/{id}                Get node details + health
PUT    /nodes/{id}                Update node config
DELETE /nodes/{id}                Remove node (must be offline)

── Node Actions ───────────────────────────────────────────────
POST   /nodes/{id}/enroll         Start enrollment
POST   /nodes/{id}/restart        Restart all services
POST   /nodes/{id}/health-check   Force immediate health check

── Maintenance ────────────────────────────────────────────────
POST   /nodes/{id}/maintenance/drain     Start draining
POST   /nodes/{id}/maintenance/planned   Schedule maintenance
POST   /nodes/{id}/maintenance/immediate Immediate offline
POST   /nodes/{id}/maintenance/complete  End maintenance, recover
DELETE /nodes/{id}/maintenance           Cancel maintenance

── Roles ──────────────────────────────────────────────────────
GET    /roles                     List available roles
GET    /roles/{id}                Role details + requirements
POST   /nodes/{id}/role           Change node role

── Deployments ────────────────────────────────────────────────
GET    /deployments               List deployments (active + history)
POST   /deployments/update        Start rolling update
POST   /deployments/role-swap     Blue-green role swap
GET    /deployments/{id}          Deployment status + progress
POST   /deployments/{id}/rollback Trigger manual rollback
DELETE /deployments/{id}          Cancel pending deployment

── Health ─────────────────────────────────────────────────────
GET    /health                    Admin machine health
GET    /health/fleet              Fleet-wide health summary
GET    /health/history            Health event history

── Maintenance Windows ────────────────────────────────────────
GET    /maintenance-windows       List scheduled windows
POST   /maintenance-windows       Schedule new window
DELETE /maintenance-windows/{id}  Cancel scheduled window
```

### WebSocket Endpoints

```
/ws/events        Real-time state changes, health events
/ws/deployments   Live deployment progress
/ws/heartbeats    Agent heartbeat stream
```

## Reconciliation Loop

The reconciler runs every 30 seconds on the admin machine:

```
1. Collect State
   - Read DB state
   - Check heartbeats
   - Pull-check if no heartbeat >60s

2. Evaluate Health
   - For each node: heartbeat age, service status, resource thresholds

3. Detect Drift
   - ONLINE but no heartbeat → DEGRADED
   - DEGRADED but healthy → ONLINE
   - DEGRADED >5min → trigger remediate

4. Execute Actions (Conservative)
   - Restart services ✓
   - Alert humans ✓
   - Auto re-enroll ✗
   - Auto role change ✗

5. Log & Notify
   - State transitions
   - WebSocket push
   - Alerts if ERROR
```

### Remediation Actions

| Condition | Action | Automatic? |
|-----------|--------|------------|
| Service down, node reachable | Restart service via SSH | ✅ Yes |
| No heartbeat <2min | Pull health check | ✅ Yes |
| No heartbeat >5min | Mark DEGRADED, alert | ✅ Yes |
| Restart failed 3x | Mark ERROR, alert | ✅ Yes |
| Node unreachable | Mark ERROR, alert | ✅ Yes |
| Disk >90% | Alert only | ✅ Yes |
| Re-enrollment needed | Alert, wait for human | ❌ No |

### Rollback Trigger

During deployment, if health fails for 5 minutes (10 consecutive 30s checks), automatic rollback is triggered.

## Deployment Strategies

### Update Strategies by Service Type

**Stateless Services** (frontend, browser, npu-worker):
- Strategy: `BLUE_GREEN_SWAP`
- Borrow node installs role → switch traffic → update original → switch back
- Downtime: 0

**Stateful Services** (redis, ai-stack):
- Strategy A: `REPLICATED_SWAP` (zero-downtime)
  - Borrow node as replica → sync data → promote → update original
  - Downtime: 0, Complexity: High

- Strategy B: `MAINTENANCE_WINDOW` (with downtime)
  - Backup → stop → update → restart
  - Downtime: 5-30 min, Complexity: Low

### Blue-Green with Role Borrowing Example

**Goal**: Update Redis with zero downtime using NPU Worker as standby

```
Phase 1: PREPARE STANDBY
   - NPU Worker: drain + purge npu role
   - NPU Worker: install redis role

Phase 2: DATA SYNC
   - NPU Worker becomes Redis replica
   - Sync data from primary

Phase 3: SWITCHOVER
   - NPU Worker promoted to primary
   - Original Redis enters maintenance

Phase 4: UPDATE ORIGINAL
   - Perform update on original Redis

Phase 5: SWITCHBACK + CLEANUP
   - Traffic restored to original Redis
   - NPU Worker: purge redis + restore npu role
```

### Rollback Points

| Phase | Failure | Rollback Action |
|-------|---------|-----------------|
| 1 | Can't install role | Restore original role, abort |
| 2 | Sync fails | Restore original role, abort |
| 3 | Standby health fails | Switch back to original |
| 4 | Update fails | Keep standby as primary, alert |
| 5 | Can't restore | Alert, standby stays temporarily |

## Node Agent

### Agent Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Node Agent (per VM)                       │
│                    ~200 lines Python                         │
│                                                              │
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │   Heartbeat     │  │  Local Health   │                   │
│  │   Sender        │  │   Collector     │                   │
│  │ - Every 30s     │  │ - systemd status│                   │
│  │ - Push to admin │  │ - Port checks   │                   │
│  │ - Buffer offline│  │ - Disk/CPU/RAM  │                   │
│  └─────────────────┘  └─────────────────┘                   │
│                                                              │
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │   Event Buffer  │  │  Command        │                   │
│  │ - SQLite local  │  │  Receiver       │                   │
│  │ - 24hr retention│  │ - mTLS auth     │                   │
│  │ - Sync on       │  │ - Restart svc   │                   │
│  │   reconnect     │  │ - Drain mode    │                   │
│  └─────────────────┘  └─────────────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

### Agent Responsibilities

| Component | Function | Admin Offline Behavior |
|-----------|----------|------------------------|
| Heartbeat Sender | Push health every 30s | Buffer locally, retry |
| Local Health Collector | Check services, resources | Continues collecting |
| Event Buffer | Store events locally | Accumulate, sync later |
| Command Receiver | Accept commands from admin | Reject (no auth) |

### Agent Does NOT

- Make remediation decisions
- Start/stop services autonomously (systemd does that)
- Communicate with other nodes

## Admin Machine Bootstrap

### Installation Sequence

1. **Provision VM**: Fresh Ubuntu 22.04/24.04, 2 CPU, 4GB RAM, 40GB disk
2. **Run Bootstrap Script**: Installs Python, Ansible, SLM, PKI CA
3. **Configure**: Edit `/opt/autobot-admin/config/admin.yaml`
4. **Start Services**: `systemctl start autobot-slm autobot-reconciler`
5. **Access UI**: `https://172.16.168.10:8443` - setup wizard

### Directory Structure

```
/opt/autobot-admin/
├── bin/
│   ├── slm-server           # FastAPI entrypoint
│   └── reconciler           # Reconciler entrypoint
├── config/
│   └── admin.yaml           # Main config
├── data/
│   ├── slm.db               # SQLite state database
│   └── events/              # Buffered events
├── keys/
│   └── fleet_key            # SSH key for fleet access
├── pki/
│   ├── ca/
│   │   ├── ca-cert.pem
│   │   └── ca-key.pem
│   └── nodes/
│       └── {node}/
├── ansible/
│   ├── inventory/
│   │   └── fleet.yml        # Auto-generated from DB
│   ├── playbooks/
│   └── roles/
├── ui/
│   └── dist/                # Vue admin UI build
├── venv/                    # Python virtualenv
└── logs/
```

### Systemd Services

- `autobot-slm.service` - FastAPI backend on :8443
- `autobot-reconciler.service` - Background reconciliation loop
- `autobot-agent.service` - Self-monitoring agent

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Control plane | API-driven | Integrates with existing FastAPI/Vue patterns |
| State storage | SQLite | Simple, survives Redis outages, already proven |
| Remediation mode | Conservative | Stability first - auto-restart, human approval for re-enroll |
| Health checks | Hybrid push/pull | Fast detection + reliability fallback |
| Deployment strategy | Blue-green + role borrowing | Zero-downtime with minimal resources |
| Stateful updates | Replicated or maintenance window | Flexibility based on situation |
| Role cleanup | Full purge | Clean slate eliminates conflicts |
| Rollback trigger | Automatic (5min timeout) | Fast recovery without human intervention |
| Admin downtime | Fleet continues | Management plane for changes, not runtime |

## Implementation Phases

### Phase 1: Foundation ✅ COMPLETE

- [x] Implement SQLite schema and models (`backend/models/infrastructure.py`)
- [x] Build core state machine logic (`backend/services/slm/state_machine.py`)
- [x] Database service with CRUD operations (`backend/services/slm/db_service.py`)
- [x] REST API for nodes and heartbeats (`backend/api/slm/`)
- [x] Lightweight node agent (`src/slm/agent/`)
- [x] Ansible role for agent deployment (`ansible/roles/slm_agent/`)
- [x] Default roles initialization (frontend, redis, npu-worker, ai-stack, browser)

### Phase 2: Health & Reconciliation ✅ COMPLETE

- [x] Heartbeat collection API (`backend/api/slm/heartbeats.py`)
- [x] Reconciliation loop service (`backend/services/slm/reconciler.py`)
- [x] Conservative remediation via SSH (`backend/services/slm/remediator.py`)
- [x] WebSocket real-time updates (`backend/api/slm/websockets.py`)
- [x] Auto-start reconciler on backend startup (`backend/initialization/lifespan.py`)

### Phase 3: Deployments ✅ COMPLETE

- [x] Sequential deployment orchestrator (`backend/services/slm/deployment_orchestrator.py`)
- [x] Blue-green with role borrowing (`BlueGreenStrategy`)
- [x] Automatic rollback on health failure (configurable threshold)
- [x] Maintenance window scheduling (`MaintenanceWindowStrategy`)
- [x] Deployment REST API (`backend/api/slm/deployments.py`)
- [x] Comprehensive test coverage (72 tests)

### Phase 4: Stateful Services ✅ COMPLETE

- [x] Redis replication-based updates (`backend/services/slm/stateful_manager.py`)
  - REPLICAOF-based replication setup with sync monitoring
  - Replica promotion with REPLICAOF NO ONE
  - ReplicatedSwapStrategy for zero-downtime stateful updates
- [x] Backup/restore for maintenance windows
  - BGSAVE-triggered RDB snapshot backups
  - Checksum verification (MD5) for backup integrity
  - Full restore with service stop/start cycle
- [x] Data sync verification
  - Keyspace analysis, memory stats, persistence status
  - Error detection and health reporting
- [x] Stateful services REST API (`backend/api/slm/stateful.py`)
- [x] Comprehensive test coverage (46 tests)

### Phase 5: Admin UI
- [ ] Vue admin dashboard
- [ ] Fleet overview with health status
- [ ] Deployment wizard
- [ ] Maintenance scheduling UI

## Related Issues

- #724 - Redis password and systemd services (superseded by mTLS)
- #725 - Migrate services to mTLS authentication
