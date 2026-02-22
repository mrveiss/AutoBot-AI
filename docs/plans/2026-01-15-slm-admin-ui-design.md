# SLM Admin UI Design

> Phase 5 of Service Lifecycle Manager (Issue #726)

## Overview

The SLM Admin UI is a standalone Vue 3 application providing a dedicated management interface for the Service Lifecycle Manager. It runs on a separate admin host and will serve as the central control plane for fleet management, deployments, backups, and system monitoring.

## Architecture Decisions

### Deployment
- **Host:** 172.16.168.19 (dedicated admin machine)
- **Credentials:** autobot:autobot
- **Port:** 5174 (to avoid conflicts)
- **Directory:** `/home/kali/Desktop/AutoBot/slm-admin/`

### Technology Stack
- Vue 3 + Composition API
- TypeScript
- Tailwind CSS
- Vite
- Vue Router (multi-page SPA)
- Pinia (state management)

### Why Separate Application?
1. **Isolation:** Admin functions separated from user-facing frontend
2. **Migration path:** Settings and monitoring will migrate from main frontend
3. **Security:** Admin interface on dedicated host with separate access control
4. **Scalability:** Can evolve independently from main frontend

## Page Structure

### 1. Fleet Overview (`/`)
Primary dashboard showing real-time fleet health.

**Components:**
- `FleetHealthGrid.vue` - Visual grid of all nodes with status indicators
- `NodeCard.vue` - Individual node health card with quick actions
- `FleetSummary.vue` - Aggregate health statistics

**Features:**
- WebSocket-driven real-time updates
- Color-coded health status (green/yellow/red)
- Quick actions: restart service, drain node, view details
- Filter by role, status, health

**Data Flow:**
```
WebSocket /v1/slm/ws → useSlmWebSocket → FleetHealthGrid
REST /v1/slm/nodes → useSlmApi → Initial load
```

### 2. Deployments (`/deployments`)
Deployment wizard and role management.

**Components:**
- `DeploymentWizard.vue` - Step-by-step deployment flow
- `RoleSelector.vue` - Role assignment interface
- `DeploymentHistory.vue` - Past deployment records
- `AnsibleOutput.vue` - Live Ansible execution output

**Wizard Steps:**
1. Select target node(s)
2. Choose role(s) to deploy
3. Configure role-specific settings
4. Review and confirm
5. Execute with live progress

**Features:**
- Multi-node batch deployments
- Role dependency validation
- Rollback capability
- Deployment templates

### 3. Backups (`/backups`)
Backup and restore management for stateful services.

**Components:**
- `BackupList.vue` - List of all backups with status
- `CreateBackupDialog.vue` - New backup wizard
- `RestoreDialog.vue` - Restore confirmation with options
- `BackupSchedule.vue` - Scheduled backup configuration

**Features:**
- On-demand backup creation
- One-click restore with confirmation
- Backup verification status
- Scheduled backups (cron-style)
- Retention policy management

### 4. Maintenance (`/maintenance`)
Maintenance window scheduling and node management.

**Components:**
- `MaintenanceCalendar.vue` - Calendar view of scheduled windows
- `DrainNodeDialog.vue` - Node drain with service migration
- `MaintenanceWindow.vue` - Window configuration

**Features:**
- Schedule maintenance windows
- Drain nodes gracefully
- Automatic service migration during maintenance
- Maintenance mode indicators

### 5. Settings (`/settings`)
System configuration (migrated from main frontend).

**Components:**
- Migrated from `autobot-user-frontend/src/views/SettingsView.vue`
- Enhanced with SLM-specific settings

**Settings Categories:**
- General system settings
- SLM configuration
- Agent deployment defaults
- Notification preferences
- API endpoints

### 6. Monitoring (`/monitoring`)
Grafana dashboards and metrics (migrated from main frontend).

**Components:**
- `GrafanaDashboard.vue` - Iframe embedding with dashboard selector
- `MetricsSummary.vue` - Quick metrics overview
- Prometheus integration

**Features:**
- Embedded Grafana dashboards
- Dashboard selector/switcher
- Full-screen mode
- Direct Grafana link for advanced use

## Composables

### `useSlmApi.ts`
REST API integration for SLM endpoints.

```typescript
export function useSlmApi() {
  const api = useApi()

  return {
    // Nodes
    getNodes: () => api.get('/v1/slm/nodes'),
    getNode: (id: string) => api.get(`/v1/slm/nodes/${id}`),

    // Deployments
    createDeployment: (data) => api.post('/v1/slm/deployments', data),
    getDeployments: () => api.get('/v1/slm/deployments'),

    // Backups
    createBackup: (data) => api.post('/v1/slm/stateful/backups', data),
    getBackups: () => api.get('/v1/slm/stateful/backups'),
    restoreBackup: (id: string) => api.post(`/v1/slm/stateful/backups/${id}/restore`),

    // Replications
    getReplications: () => api.get('/v1/slm/stateful/replications'),
    startReplication: (data) => api.post('/v1/slm/stateful/replications', data),

    // Health
    getNodeHealth: (id: string) => api.get(`/v1/slm/nodes/${id}/health`),
  }
}
```

### `useSlmWebSocket.ts`
Real-time WebSocket connection for fleet updates.

```typescript
export function useSlmWebSocket() {
  const socket = ref<WebSocket | null>(null)
  const connected = ref(false)
  const events = ref<SLMEvent[]>([])

  const connect = () => {
    socket.value = new WebSocket('wss://172.16.168.20:8443/v1/slm/ws')
    // Handle messages, reconnection, etc.
  }

  const subscribe = (nodeId: string) => {
    // Subscribe to specific node updates
  }

  return { connect, disconnect, subscribe, events, connected }
}
```

### `useFleetHealth.ts`
Aggregated fleet health state management.

```typescript
export function useFleetHealth() {
  const nodes = ref<Map<string, NodeHealth>>()
  const overallHealth = computed(() => calculateOverallHealth(nodes.value))

  const updateNodeHealth = (nodeId: string, health: NodeHealth) => {
    nodes.value.set(nodeId, health)
  }

  return { nodes, overallHealth, updateNodeHealth }
}
```

## Directory Structure

```
slm-admin/
├── src/
│   ├── assets/
│   │   └── styles/
│   │       └── main.css
│   ├── components/
│   │   ├── common/
│   │   │   ├── Sidebar.vue
│   │   │   ├── Header.vue
│   │   │   └── LoadingSpinner.vue
│   │   ├── fleet/
│   │   │   ├── FleetHealthGrid.vue
│   │   │   ├── NodeCard.vue
│   │   │   └── FleetSummary.vue
│   │   ├── deployments/
│   │   │   ├── DeploymentWizard.vue
│   │   │   ├── RoleSelector.vue
│   │   │   └── DeploymentHistory.vue
│   │   ├── backups/
│   │   │   ├── BackupList.vue
│   │   │   ├── CreateBackupDialog.vue
│   │   │   └── RestoreDialog.vue
│   │   ├── maintenance/
│   │   │   ├── MaintenanceCalendar.vue
│   │   │   └── DrainNodeDialog.vue
│   │   └── monitoring/
│   │       └── GrafanaDashboard.vue
│   ├── composables/
│   │   ├── useSlmApi.ts
│   │   ├── useSlmWebSocket.ts
│   │   └── useFleetHealth.ts
│   ├── router/
│   │   └── index.ts
│   ├── stores/
│   │   └── fleet.ts
│   ├── types/
│   │   └── slm.ts
│   ├── views/
│   │   ├── FleetOverview.vue
│   │   ├── DeploymentsView.vue
│   │   ├── BackupsView.vue
│   │   ├── MaintenanceView.vue
│   │   ├── SettingsView.vue
│   │   └── MonitoringView.vue
│   ├── App.vue
│   └── main.ts
├── public/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
└── tailwind.config.js
```

## Implementation Plan

### Step 1: Project Scaffold
- Initialize Vite + Vue 3 + TypeScript project
- Configure Tailwind CSS
- Set up Vue Router with page routes
- Create base layout with sidebar

### Step 2: Core Composables
- Implement `useSlmApi.ts` with all endpoints
- Implement `useSlmWebSocket.ts` for real-time updates
- Implement `useFleetHealth.ts` for state management

### Step 3: Fleet Overview Page
- Build `FleetHealthGrid.vue` component
- Build `NodeCard.vue` with health indicators
- Integrate WebSocket for live updates
- Add filtering and quick actions

### Step 4: Deployments Page
- Build multi-step deployment wizard
- Implement role selection interface
- Add Ansible output streaming
- Build deployment history view

### Step 5: Backups Page
- Build backup list with status
- Implement create/restore dialogs
- Add backup scheduling UI
- Integrate verification status

### Step 6: Maintenance Page
- Build maintenance calendar
- Implement drain node functionality
- Add maintenance window scheduling

### Step 7: Settings & Monitoring Migration
- Migrate Settings view from main frontend
- Migrate Grafana integration
- Adapt for standalone deployment

### Step 8: Deployment Script
- Create sync script for 172.16.168.19
- Configure nginx/serve for production
- Test end-to-end functionality

## API Dependencies

The Admin UI depends on these backend endpoints (all implemented in Phases 1-4):

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/v1/slm/nodes` | GET | List all nodes |
| `/v1/slm/nodes/{id}` | GET | Node details |
| `/v1/slm/nodes/{id}/health` | GET | Node health |
| `/v1/slm/heartbeats` | POST | Agent heartbeat |
| `/v1/slm/deployments` | GET/POST | Deployment management |
| `/v1/slm/stateful/backups` | GET/POST | Backup management |
| `/v1/slm/stateful/replications` | GET/POST | Replication management |
| `/v1/slm/ws` | WebSocket | Real-time updates |

## Success Criteria

1. ✅ Standalone Vue 3 app running on 172.16.168.19
2. ✅ Real-time fleet health visualization
3. ✅ Deployment wizard with Ansible integration
4. ✅ Backup/restore functionality
5. ✅ Maintenance window scheduling
6. ✅ Settings migrated from main frontend
7. ✅ Grafana dashboards migrated and working
8. ✅ All pages responsive and functional
