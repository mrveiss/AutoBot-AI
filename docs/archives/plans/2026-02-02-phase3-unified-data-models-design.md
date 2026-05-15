# Phase 3: Unify Data Models

**Issue:** #737 - Consolidate duplicate node management UI
**Phase:** 3 of 3
**Date:** 2026-02-02
**Status:** Design

---

## Summary

Unify node data models across the codebase by creating shared constants for roles, extracting hardcoded role metadata, and ensuring type consistency between frontend and backend.

## Current State Analysis

### Backend (Source of Truth)

**slm-server/models/database.py:**
```python
class Node(Base):
    node_id = Column(String(64))  # Unique identifier
    roles = Column(JSON)          # Array of roles
    auth_method = Column(String(20), default="key")
```

**slm-server/api/deployments.py:**
- `AVAILABLE_ROLES` - Complete role definitions with metadata
- 10 roles: slm-agent, redis, backend, frontend, llm, ai-stack, npu-worker, browser-automation, monitoring, vnc

### Frontend

**slm-admin/src/types/slm.ts:**
- Well-defined `SLMNode`, `NodeRole`, `RoleInfo` types
- Includes all 10 roles + 'vnc'

**Issues Found:**
1. `FleetOverview.vue` has hardcoded `availableRoles` array (missing 'vnc')
2. `FleetOverview.vue` has hardcoded `roleData` duplicating backend definitions
3. No fallback constants when API unavailable
4. `InfrastructureMonitor.vue` uses separate local VM definitions (intentional - different purpose)

## Goals

1. Create shared role constants file for fallback data
2. Update FleetOverview.vue to use fleet store's `availableRoles` from API
3. Remove hardcoded `roleData` duplication
4. Document intentional separation of InfrastructureMonitor.vue
5. Add shared status utilities for consistency

## Solution Design

### 1. Create Role Constants (Fallback)

**File:** `slm-admin/src/constants/node-roles.ts`

```typescript
/**
 * Node Role Constants
 *
 * Fallback role definitions when API is unavailable.
 * Source of truth: slm-server/api/deployments.py:AVAILABLE_ROLES
 */

import type { NodeRole, RoleCategory } from '@/types/slm'

export interface RoleMetadata {
  name: NodeRole
  displayName: string
  description: string
  category: RoleCategory
  tools: string[]
}

export const NODE_ROLE_METADATA: Record<NodeRole, RoleMetadata> = {
  'slm-agent': {
    name: 'slm-agent',
    displayName: 'SLM Agent',
    description: 'SLM monitoring agent for node health reporting',
    category: 'core',
    tools: ['systemd', 'journalctl', 'htop', 'netstat'],
  },
  // ... all roles
}

export const DEFAULT_ROLES: NodeRole[] = Object.keys(NODE_ROLE_METADATA) as NodeRole[]
```

### 2. Update FleetOverview.vue

**Before:**
```typescript
const availableRoles: NodeRole[] = ['slm-agent', 'redis', ...] // Hardcoded, missing vnc
const roleData: Record<NodeRole, {...}> = { ... } // Duplicated metadata
```

**After:**
```typescript
import { NODE_ROLE_METADATA, DEFAULT_ROLES } from '@/constants/node-roles'

// Use API data, fallback to constants
const availableRoles = computed(() =>
  fleetStore.availableRoles.length > 0
    ? fleetStore.availableRoles.map(r => r.name)
    : DEFAULT_ROLES
)

// Get role metadata from API or constants
function getRoleMetadata(role: NodeRole) {
  const apiRole = fleetStore.availableRoles.find(r => r.name === role)
  if (apiRole) return apiRole
  return NODE_ROLE_METADATA[role]
}
```

### 3. Document InfrastructureMonitor Separation

**InfrastructureMonitor.vue** is intentionally different:
- Purpose: Monitor fixed infrastructure VMs from SSOT config
- Data source: SSOT config (`config.vm.*`) + fleet store health data
- Role: Human-readable description, not technical NodeRole

Add JSDoc comment documenting this separation.

### 4. Shared Status Utilities

**File:** `slm-admin/src/utils/node-status.ts`

```typescript
export function getStatusColor(status: NodeStatus | HealthStatus): string {
  // Consolidated status color logic
}

export function getStatusBadgeClass(status: string): string {
  // Badge styling for status display
}
```

---

## Files to Modify

| Action | File | Change |
|--------|------|--------|
| Create | `constants/node-roles.ts` | Role constants and metadata |
| Create | `utils/node-status.ts` | Shared status utilities |
| Update | `views/FleetOverview.vue` | Use fleet store & constants |
| Update | `views/monitoring/InfrastructureMonitor.vue` | Add separation doc |
| Update | `stores/fleet.ts` | Ensure roles loaded on init |

## Implementation Tasks

### Task 1: Create node-roles.ts constants
- Create `slm-admin/src/constants/node-roles.ts`
- Define `NODE_ROLE_METADATA` with all 10 roles
- Export `DEFAULT_ROLES` array
- Commit: `feat(slm): add node role constants (#737)`

### Task 2: Create node-status.ts utilities
- Create `slm-admin/src/utils/node-status.ts`
- Export `getStatusColor()`, `getStatusBadgeClass()`
- Commit: `feat(slm): add shared status utilities (#737)`

### Task 3: Update FleetOverview.vue
- Import constants and utilities
- Replace hardcoded `availableRoles` with computed from store
- Replace `roleData` with `getRoleMetadata()` function
- Commit: `refactor(slm): use shared role constants in FleetOverview (#737)`

### Task 4: Update InfrastructureMonitor.vue
- Add JSDoc documenting separation from SLM nodes
- Use shared status utilities
- Commit: `refactor(slm): document InfrastructureMonitor separation (#737)`

### Task 5: Update fleet store
- Ensure `fetchRoles()` called during initialization
- Add `getRoleInfo()` method
- Commit: `refactor(slm): enhance fleet store role management (#737)`

---

## Acceptance Criteria

- [ ] Role constants file created with all 10 roles
- [ ] FleetOverview uses store/constants (no hardcoded roleData)
- [ ] Status utilities shared across components
- [ ] InfrastructureMonitor documented as separate concern
- [ ] No regression in existing functionality

---

## Out of Scope

- **Backend changes**: AVAILABLE_ROLES is already the source of truth
- **API changes**: Existing `/deployments/roles` endpoint is sufficient
- **InfrastructureMonitor refactoring**: Intentionally separate, different purpose
