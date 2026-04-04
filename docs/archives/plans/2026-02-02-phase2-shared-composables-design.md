# Phase 2: Shared Composables & Fleet Tools Consolidation

**Issue:** #737 - Consolidate duplicate node management UI
**Phase:** 2 of 3
**Date:** 2026-02-02
**Status:** Design Approved

---

## Summary

Remove duplicate Fleet Tools that overlap with NodeCard/panel functionality. Create shared composables to unify connection testing, health checking, and service management across the SLM Admin frontend.

## Goals

1. Remove 3 duplicate tools from FleetToolsTab (Network Test, Health Check, Service Manager)
2. Create 3 shared composables for reusable node operations
3. Update FleetToolsTab to use remaining 3 tools (Log Viewer, Redis CLI, Command Runner)
4. Ensure no loss of functionality

## Tool Evaluation

| Fleet Tool | Overlap | Decision | Reason |
|-----------|---------|----------|--------|
| Network Test | NodeCard "Test" action | **Remove** | FleetOverview already has connection test modal |
| Deep Health Check | NodeCard health display | **Remove** | NodeLifecyclePanel provides deep inspection |
| Service Manager | NodeServicesPanel | **Remove** | Panel has start/stop/restart + logs |
| Log Viewer | - | **Keep** | Quick cross-node log search |
| Redis CLI | - | **Keep** | Specialized database tool |
| Command Runner | - | **Keep** | Admin shell access |

## New Composables

### 1. useNodeConnectionTest.ts

**Purpose:** Unified connection testing for nodes.

**Location:** `slm-admin/src/composables/useNodeConnectionTest.ts`

```typescript
interface ConnectionTestResult {
  success: boolean
  hostname?: string
  os_info?: string
  latency_ms?: number
  error?: string
  message?: string
}

interface UseNodeConnectionTestReturn {
  isLoading: Ref<boolean>
  result: Ref<ConnectionTestResult | null>
  error: Ref<string | null>
  testByNodeId(nodeId: string): Promise<ConnectionTestResult>
  testByAddress(params: ConnectionParams): Promise<ConnectionTestResult>
  reset(): void
}
```

**Consumers:** FleetOverview, NodeCard, AddNodeModal

---

### 2. useNodeHealth.ts

**Purpose:** Real-time node health with deep check capability.

**Location:** `slm-admin/src/composables/useNodeHealth.ts`

```typescript
interface UseNodeHealthReturn {
  health: Ref<NodeHealth | null>
  deepHealth: Ref<DeepHealthResult | null>
  isLoading: Ref<boolean>
  error: Ref<string | null>
  fetchHealth(): Promise<NodeHealth>
  deepCheck(): Promise<DeepHealthResult>
  subscribe(): void
  unsubscribe(): void
}
```

**Consumers:** NodeCard, NodeLifecyclePanel, FleetSummary

---

### 3. useNodeServices.ts

**Purpose:** Service management operations for a node.

**Location:** `slm-admin/src/composables/useNodeServices.ts`

```typescript
interface UseNodeServicesReturn {
  services: Ref<Service[]>
  isLoading: Ref<boolean>
  error: Ref<string | null>
  fetchServices(): Promise<Service[]>
  startService(name: string): Promise<ServiceActionResult>
  stopService(name: string): Promise<ServiceActionResult>
  restartService(name: string): Promise<ServiceActionResult>
  getLogs(name: string, lines?: number): Promise<string>
}
```

**Consumers:** NodeServicesPanel, FleetToolsTab (Log Viewer only)

---

## Files to Modify

| Action | File | Change |
|--------|------|--------|
| Create | `composables/useNodeConnectionTest.ts` | Connection testing composable |
| Create | `composables/useNodeHealth.ts` | Health monitoring composable |
| Create | `composables/useNodeServices.ts` | Service management composable |
| Update | `FleetToolsTab.vue` | Remove 3 tools, keep 3, use composables |
| Update | `FleetOverview.vue` | Use useNodeConnectionTest |
| Update | `NodeServicesPanel.vue` | Use useNodeServices |
| Deprecate | `useFleetHealth.ts` | Mark deprecated after migration |

## Implementation Order

1. Create useNodeConnectionTest.ts
2. Create useNodeServices.ts
3. Create useNodeHealth.ts
4. Update FleetToolsTab.vue - remove 3 duplicate tools
5. Update FleetOverview.vue - use connection test composable
6. Update NodeServicesPanel.vue - use services composable
7. Deprecate useFleetHealth.ts

## Acceptance Criteria

- [ ] 3 new composables created with full TypeScript types
- [ ] FleetToolsTab reduced to 3 tools (Log Viewer, Redis CLI, Command Runner)
- [ ] Connection test works from FleetOverview and AddNodeModal
- [ ] Service management works from NodeServicesPanel
- [ ] No functionality loss
- [ ] useFleetHealth.ts marked deprecated

---

## Implementation Tasks

> **For Claude:** Use superpowers:subagent-driven-development to execute these tasks.

### Task 1: Create useNodeConnectionTest.ts
- Create `slm-admin/src/composables/useNodeConnectionTest.ts`
- Wrap `useSlmApi().testConnection()` with reactive state
- Provide `testByNodeId()` and `testByAddress()` methods
- Commit: `feat(slm): add useNodeConnectionTest composable (#737)`

### Task 2: Create useNodeServices.ts
- Create `slm-admin/src/composables/useNodeServices.ts`
- Wrap service API methods with reactive state
- Accept `nodeId` as MaybeRef for reactivity
- Commit: `feat(slm): add useNodeServices composable (#737)`

### Task 3: Create useNodeHealth.ts
- Create `slm-admin/src/composables/useNodeHealth.ts`
- Integrate with useSlmWebSocket for real-time updates
- Provide `fetchHealth()`, `deepCheck()`, `subscribe()`
- Commit: `feat(slm): add useNodeHealth composable (#737)`

### Task 4: Update FleetToolsTab.vue
- Remove tools: network-test, health-check, service-restart
- Keep tools: log-viewer, redis-cli, ansible-runner
- Use useNodeServices for log viewer
- Commit: `refactor(slm): remove duplicate tools from FleetToolsTab (#737)`

### Task 5: Update FleetOverview.vue
- Import and use useNodeConnectionTest
- Replace inline connection test logic
- Commit: `refactor(slm): use useNodeConnectionTest in FleetOverview (#737)`

### Task 6: Deprecate useFleetHealth.ts
- Add @deprecated JSDoc notice
- Commit: `refactor(slm): deprecate useFleetHealth composable (#737)`

### Task 7: Update GitHub Issue #737
- Add Phase 2 completion comment
