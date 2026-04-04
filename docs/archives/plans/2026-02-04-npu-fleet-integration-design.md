# NPU Fleet Integration Design

> **Date:** 2026-02-04
> **Status:** Approved
> **Related Issues:** #255 (Service Authentication), #729 (Layer Separation)
> **Author:** mrveiss

---

## Overview

This design integrates NPU worker management into the Fleet system within SLM Admin. NPU workers become fleet nodes with the `npu-worker` role, leveraging the existing node deployment infrastructure while adding NPU-specific capabilities.

### Goals
1. Integrate NPU workers as fleet nodes with `npu-worker` role
2. Auto-detect NPU capabilities via health/models endpoints
3. Provide NPU-specific management UI as a Fleet tab
4. Ensure all service-to-service communication uses HMAC-SHA256 authentication (Issue #255)
5. Deprecate standalone NPUWorkersSettings.vue

---

## Section 1: Architecture Overview

### Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         SLM Admin                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ Nodes Tab   │  │ Fleet Tools │  │ NPU Workers Tab (NEW)   │  │
│  │             │  │ Tab         │  │ - NPUNodeCard           │  │
│  │             │  │             │  │ - NPUDetailsPanel       │  │
│  │             │  │             │  │ - AssignNPURoleModal    │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Backend API                                 │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ Existing:                    New:                           ││
│  │ - GET /api/fleet/nodes       - GET /api/nodes/{id}/npu/status││
│  │ - POST /api/fleet/nodes      - POST /api/npu/load-balancing ││
│  │ - PATCH /api/fleet/nodes/{id}                               ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ (ServiceHTTPClient - HMAC auth)
┌─────────────────────────────────────────────────────────────────┐
│                      NPU Workers                                 │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐       │
│  │ Node A        │  │ Node B        │  │ Node C        │       │
│  │ role: npu     │  │ role: npu     │  │ role: npu     │       │
│  │ models: [...]│  │ models: [...]│  │ models: [...]│       │
│  └───────────────┘  └───────────────┘  └───────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

### Fleet Store Changes (`slm-admin/src/stores/fleet.ts`)

```typescript
// New computed property for NPU nodes
const npuNodes = computed(() =>
  nodes.value.filter(n => n.roles.includes('npu-worker'))
)

// NPU capabilities cache
const npuCapabilities = ref<Map<string, NPUCapabilities>>(new Map())

interface NPUCapabilities {
  models: string[]
  maxConcurrent: number
  memoryGB: number
  deviceType: 'intel-npu' | 'nvidia-gpu' | 'amd-gpu'
  utilization: number
}
```

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/nodes/{id}/npu/status` | GET | Get NPU-specific status for a node |
| `/api/npu/load-balancing` | POST | Configure load balancing across NPU nodes |

---

## Section 2: Frontend Components

### Component Hierarchy

```
FleetOverview.vue
├── NodesTab.vue (existing)
├── FleetToolsTab.vue (existing)
└── NPUWorkersTab.vue (NEW)
    ├── NPUNodeCard.vue (displays each NPU node)
    ├── NPUDetailsPanel.vue (expanded view with models/stats)
    └── AssignNPURoleModal.vue (assign npu-worker role to node)
```

### NPUWorkersTab.vue

Main container component that displays:
- Grid of NPU nodes using NPUNodeCard
- Summary stats (total NPU nodes, total models, avg utilization)
- "Assign NPU Role" button to open modal
- Load balancing configuration section

```vue
<template>
  <div class="npu-workers-tab">
    <!-- Summary Stats -->
    <div class="stats-row">
      <StatCard title="NPU Nodes" :value="npuNodes.length" />
      <StatCard title="Total Models" :value="totalModels" />
      <StatCard title="Avg Utilization" :value="avgUtilization + '%'" />
    </div>

    <!-- Actions -->
    <div class="actions">
      <Button @click="showAssignModal = true">Assign NPU Role</Button>
      <Button @click="refreshAll">Refresh All</Button>
    </div>

    <!-- Node Grid -->
    <div class="node-grid">
      <NPUNodeCard
        v-for="node in npuNodes"
        :key="node.id"
        :node="node"
        @select="selectedNode = node"
      />
    </div>

    <!-- Details Panel (slide-out) -->
    <NPUDetailsPanel
      v-if="selectedNode"
      :node="selectedNode"
      @close="selectedNode = null"
    />

    <!-- Assign Role Modal -->
    <AssignNPURoleModal
      v-model:visible="showAssignModal"
      :available-nodes="nonNpuNodes"
    />
  </div>
</template>
```

### NPUNodeCard.vue

Displays individual NPU node with:
- Node name and status indicator
- Device type badge (Intel NPU, NVIDIA GPU, etc.)
- Loaded models count
- Current utilization bar
- Quick actions (view details, remove role)

### NPUDetailsPanel.vue

Expanded view showing:
- Full model list with load/unload actions
- Performance metrics (inference time, throughput)
- Memory usage breakdown
- Request queue status
- Historical utilization chart

### AssignNPURoleModal.vue

Modal for assigning `npu-worker` role to existing nodes:
- List of nodes without NPU role
- Auto-detection status for each
- Confirmation with capability preview

---

## Section 3: Backend API & Service Authentication

### Auto-Detection Flow

When a node receives the `npu-worker` role:

```python
async def detect_npu_capabilities(node_id: str) -> NPUCapabilities:
    """
    Auto-detect NPU capabilities for a node.
    Uses ServiceHTTPClient for authenticated communication.
    """
    node = await get_node(node_id)

    # Use authenticated client (Issue #255)
    client = ServiceHTTPClient(service_id="main-backend")

    try:
        # Probe health endpoint
        health = await client.get(f"http://{node.ip}:8081/health")

        # Get available models
        models = await client.get(f"http://{node.ip}:8081/models")

        return NPUCapabilities(
            models=models.get('available', []),
            maxConcurrent=health.get('max_concurrent', 4),
            memoryGB=health.get('memory_gb', 8),
            deviceType=detect_device_type(health),
            utilization=health.get('utilization', 0)
        )
    except Exception as e:
        logger.error(f"NPU detection failed for {node_id}: {e}")
        return None
```

### ServiceHTTPClient Integration (Issue #255)

Update `src/npu_integration.py` to use authenticated client:

```python
# BEFORE (vulnerable)
from src.utils.http_client import get_http_client
self._http_client = get_http_client()

# AFTER (authenticated)
from backend.utils.service_client import ServiceHTTPClient
self._http_client = ServiceHTTPClient(service_id="main-backend")
```

Authentication headers added automatically:
- `X-Service-ID`: Service identifier
- `X-Service-Signature`: HMAC-SHA256 signature
- `X-Service-Timestamp`: Request timestamp

Signature format: `HMAC-SHA256(service_key, "service_id:method:path:timestamp")`

### New API Endpoints

#### GET /api/nodes/{node_id}/npu/status

Returns NPU-specific status for a node:

```json
{
  "node_id": "node-123",
  "capabilities": {
    "models": ["phi-3-mini", "llama-3.2-1b"],
    "maxConcurrent": 4,
    "memoryGB": 16,
    "deviceType": "intel-npu",
    "utilization": 45
  },
  "loadedModels": ["phi-3-mini"],
  "queueDepth": 2,
  "lastHealthCheck": "2026-02-04T10:30:00Z"
}
```

#### POST /api/npu/load-balancing

Configure load balancing strategy:

```json
{
  "strategy": "round-robin" | "least-loaded" | "model-affinity",
  "modelAffinity": {
    "phi-3-mini": ["node-123", "node-456"],
    "llama-3.2-1b": ["node-789"]
  }
}
```

---

## Implementation Plan

### Phase 1: Role & Store Updates
1. Add `npu-worker` role to `slm-admin/src/constants/node-roles.ts`
2. Update `fleet.ts` store with `npuNodes` computed and `npuCapabilities` map
3. Add NPU capability types to shared types

### Phase 2: Backend Authentication (Issue #255)
1. Update `NPUWorkerClient` in `src/npu_integration.py` to use `ServiceHTTPClient`
2. Add `/api/nodes/{id}/npu/status` endpoint
3. Add `/api/npu/load-balancing` endpoint
4. Implement auto-detection logic

### Phase 3: Frontend Components
1. Create `NPUWorkersTab.vue` container
2. Create `NPUNodeCard.vue` display component
3. Create `NPUDetailsPanel.vue` detail view
4. Create `AssignNPURoleModal.vue` role assignment
5. Update `FleetOverview.vue` to add NPU Workers tab

### Phase 4: Cleanup
1. Mark `NPUWorkersSettings.vue` as deprecated
2. Add redirect from old route to new Fleet tab
3. Update documentation

---

## Security Considerations

1. **Service Authentication**: All backend-to-NPU-worker communication uses HMAC-SHA256 via ServiceHTTPClient
2. **Role Assignment**: Only admin users can assign `npu-worker` role
3. **Capability Detection**: Timeouts and error handling prevent hung detection
4. **Input Validation**: All API inputs validated before processing

---

## Testing Strategy

1. **Unit Tests**: Store computations, capability detection logic
2. **Integration Tests**: API endpoints with mocked NPU workers
3. **E2E Tests**: Full flow from role assignment to capability display
4. **Security Tests**: Verify authentication headers present on all outbound requests

---

## Deprecation Plan

The standalone `NPUWorkersSettings.vue` at `/settings/admin/npu-workers` will be:
1. Marked deprecated with banner pointing to Fleet tab
2. Route redirected after 2 releases
3. Component removed in subsequent release
