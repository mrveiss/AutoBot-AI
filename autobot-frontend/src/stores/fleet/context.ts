// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Fleet store state and context (#19834). The state is the SLM fleet store's, ref for ref;
 * every slice reads and writes it through one `FleetCtx`.
 */
import { ref, type Ref } from 'vue'
import type {
  FleetUpdateSummary,
  NodeEvent,
  NPUFleetMetrics,
  NPULoadBalancingConfig,
  NPUNodeStatus,
  NPUWorkerConfig,
  NodeUpdateRecord,
  RoleInfo,
  SLMNode,
} from '@autobot/slm-contract'
import { slmApi, type SlmApi } from '@/utils/slmApi'
import type { NodeCertificate } from '@/utils/slmApi/nodes'

export interface FleetState {
  nodes: Ref<Map<string, SLMNode>>
  isLoading: Ref<boolean>
  error: Ref<string | null>
  lastRefresh: Ref<Date | null>
  /** Currently selected node for detail view */
  selectedNode: Ref<SLMNode | null>
  /** Cache of node events by node ID */
  nodeEvents: Ref<Map<string, NodeEvent[]>>
  /** Cache of certificate status by node ID */
  certificateStatus: Ref<Map<string, NodeCertificate>>
  /** Cache of available updates by node ID */
  nodeUpdates: Ref<Map<string, NodeUpdateRecord[]>>
  /** Available roles from the backend */
  availableRoles: Ref<RoleInfo[]>
  /** NPU capabilities cache by node ID (Issue #255) */
  npuCapabilities: Ref<Map<string, NPUNodeStatus>>
  npuLoadBalancingConfig: Ref<NPULoadBalancingConfig | null>
  /** Fleet-wide update summary (#682) */
  fleetUpdateSummary: Ref<FleetUpdateSummary | null>
  /** Cached fleet-level NPU metrics (Issue #590) */
  npuFleetMetrics: Ref<NPUFleetMetrics | null>
  /** Per-node NPU config cache (Issue #590) */
  npuWorkerConfigs: Ref<Map<string, NPUWorkerConfig>>
}

export interface FleetCtx {
  api: SlmApi
  state: FleetState
}

export function createFleetState(): FleetState {
  return {
    nodes: ref(new Map()),
    isLoading: ref(false),
    error: ref(null),
    lastRefresh: ref(null),
    selectedNode: ref(null),
    nodeEvents: ref(new Map()),
    certificateStatus: ref(new Map()),
    nodeUpdates: ref(new Map()),
    availableRoles: ref([]),
    npuCapabilities: ref(new Map()),
    npuLoadBalancingConfig: ref(null),
    fleetUpdateSummary: ref(null),
    npuFleetMetrics: ref(null),
    npuWorkerConfigs: ref(new Map()),
  }
}

export function createFleetContext(api: SlmApi = slmApi): FleetCtx {
  return { api, state: createFleetState() }
}

/** Records a failure on the store's `error`, as every action did inline before the split. */
export function reportError(ctx: FleetCtx, err: unknown, fallback: string): void {
  ctx.state.error.value = err instanceof Error ? err.message : fallback
}
