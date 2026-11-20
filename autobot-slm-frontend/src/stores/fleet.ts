// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Fleet Store
 *
 * Pinia store for global fleet state management.
 * Provides comprehensive node management including CRUD operations,
 * enrollment, certificates, events, and updates.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  SLMNode,
  NodeHealth,
  FleetSummary,
  FleetUpdateSummary,
  NodeUpdateSummary,
  NodeHealthStatus,
  NodeRole,
  NodeCreate,
  NodeUpdate,
  NodeEvent,
  NodeEventFilters,
  CertificateInfo,
  NodeUpdateRecord,
  NodeUpdateCheckResponse,
  ConnectionTestResult,
  RoleInfo,
  NPUNodeStatus,
  NPULoadBalancingConfig,
  NPUFleetMetrics,
  NPUWorkerMetrics,
  NPUWorkerConfig,
} from '@/types/slm'
import { useSlmApi } from '@/composables/useSlmApi'
import i18n from '@/i18n'
import { PartialListError } from '@/utils/fetchAllPages'

/** A caught value's message; the original error text, never a hard-coded English fallback. */
const errorText = (err: unknown): string => (err instanceof Error ? err.message : String(err))
import { incompleteOf, reconcileUpdateSummary, toNodeMap } from './fleetHelpers'
import type { NodeListIncomplete } from './fleetHelpers'

export const useFleetStore = defineStore('fleet', () => {
  const api = useSlmApi()

  // ============================================================
  // State
  // ============================================================

  const nodes = ref<Map<string, SLMNode>>(new Map())
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const lastRefresh = ref<Date | null>(null)
  /** Set when the node list held is not the whole fleet (#21584); null when it is. */
  const incomplete = ref<NodeListIncomplete | null>(null)
  /** Why the last node-list read failed outright; null after a read that succeeded, empty or not. */
  const nodesError = ref<string | null>(null)
  let nodesRequest = 0 // newest fetchNodes call

  /** Currently selected node for detail view */
  const selectedNode = ref<SLMNode | null>(null)

  /** Cache of node events by node ID */
  const nodeEvents = ref<Map<string, NodeEvent[]>>(new Map())

  /** Cache of certificate status by node ID */
  const certificateStatus = ref<Map<string, CertificateInfo>>(new Map())

  /** Cache of available updates by node ID */
  const nodeUpdates = ref<Map<string, NodeUpdateRecord[]>>(new Map())

  /** Available roles from the backend */
  const availableRoles = ref<RoleInfo[]>([])

  /** NPU capabilities cache by node ID (Issue #255 - NPU Fleet Integration) */
  const npuCapabilities = ref<Map<string, NPUNodeStatus>>(new Map())

  /** NPU load balancing configuration */
  const npuLoadBalancingConfig = ref<NPULoadBalancingConfig | null>(null)

  /** Fleet-wide update summary (#682) */
  const fleetUpdateSummary = ref<FleetUpdateSummary | null>(null)

  // ============================================================
  // Getters
  // ============================================================

  const nodeList = computed(() => Array.from(nodes.value.values()))

  const fleetSummary = computed<FleetSummary>(() => {
    let healthy = 0
    let degraded = 0
    let unhealthy = 0
    let offline = 0

    for (const node of nodes.value.values()) {
      switch (node.status) {
        case 'online':
          healthy++
          break
        case 'degraded':
          degraded++
          break
        case 'error':
          unhealthy++
          break
        case 'offline':
        case 'pending':
        case 'enrolling':
          offline++
          break
        default:
          offline++
      }
    }

    return {
      total_nodes: nodes.value.size,
      healthy_nodes: healthy,
      degraded_nodes: degraded,
      unhealthy_nodes: unhealthy,
      offline_nodes: offline,
    }
  })

  const overallHealth = computed<NodeHealthStatus>(() => {
    const summary = fleetSummary.value
    if (summary.total_nodes === 0) return 'unknown'
    if (summary.unhealthy_nodes > 0 || summary.offline_nodes > 0) return 'unhealthy'
    if (summary.degraded_nodes > 0) return 'degraded'
    return 'healthy'
  })

  /** Get events for currently selected node */
  const selectedNodeEvents = computed<NodeEvent[]>(() => {
    if (!selectedNode.value) return []
    return nodeEvents.value.get(selectedNode.value.node_id) || []
  })

  /** Get certificate info for currently selected node */
  const selectedNodeCertificate = computed<CertificateInfo | null>(() => {
    if (!selectedNode.value) return null
    return certificateStatus.value.get(selectedNode.value.node_id) || null
  })

  /** Get all nodes with npu-worker role (Issue #255 - NPU Fleet Integration) */
  const npuNodes = computed<SLMNode[]>(() => {
    return Array.from(nodes.value.values()).filter(
      node => node.roles.includes('npu-worker')
    )
  })

  /** Get nodes without npu-worker role (for role assignment) */
  const nonNpuNodes = computed<SLMNode[]>(() => {
    return Array.from(nodes.value.values()).filter(
      node => !node.roles.includes('npu-worker')
    )
  })

  /** Count of nodes that need updates (#682) */
  const nodesNeedingUpdates = computed(() => {
    return fleetUpdateSummary.value?.nodes_needing_updates ?? 0
  })

  // ============================================================
  // Actions - Fleet Update Summary (#682)
  // ============================================================

  /**
   * Fetch fleet-wide update summary from API.
   * Updates are supplementary info; failures are silently handled.
   */
  async function fetchFleetUpdateSummary(): Promise<void> {
    try {
      fleetUpdateSummary.value = await api.getFleetUpdateSummary()
    } catch {
      // Silently fail - updates are supplementary info
      fleetUpdateSummary.value = null
    }
  }

  /**
   * Get update summary for a specific node by ID (#682)
   */
  function getNodeUpdateSummary(nodeId: string): NodeUpdateSummary | undefined {
    return fleetUpdateSummary.value?.nodes.find(n => n.node_id === nodeId)
  }

  /** Patch one node's cached update summary after a live check (#11964); see `reconcileUpdateSummary`. */
  function reconcileNodeUpdateSummary(
    nodeId: string,
    systemUpdates: number,
    codeUpdateAvailable: boolean,
    codeStatus: string
  ): void {
    reconcileUpdateSummary(fleetUpdateSummary.value, nodeId, systemUpdates, codeUpdateAvailable, codeStatus)
  }

  // ============================================================
  // Actions - Roles
  // ============================================================

  /**
   * Fetch available roles from API
   */
  async function fetchRoles(): Promise<RoleInfo[]> {
    try {
      const roles = await api.getRoles()
      availableRoles.value = roles
      return roles
    } catch (err) {
      error.value = errorText(err)
      throw err
    }
  }

  // ============================================================
  // Actions - Node Fetching
  // ============================================================

  /**
   * Fetch all nodes from API
   */
  async function fetchNodes(): Promise<void> {
    const request = ++nodesRequest // the newest call owns every mutation; an overlapped one is stale
    isLoading.value = true
    error.value = nodesError.value = null

    try {
      const loaded = toNodeMap(await api.getNodes())
      if (request !== nodesRequest) return
      nodes.value = loaded
      incomplete.value = null
      lastRefresh.value = new Date()
    } catch (err) {
      if (request !== nodesRequest) return // superseded
      // #21584: a partial read is a flagged result, not a failure; an outright failure keeps `incomplete` as it was.
      if (err instanceof PartialListError) {
        incomplete.value = incompleteOf(err)
        nodes.value = toNodeMap(err.items as SLMNode[]) // usable data: `incomplete` is the signal, not `error`
        return
      }
      error.value = nodesError.value = err instanceof Error ? err.message : i18n.global.t('fleetOverview.loadFailedUnknown')
      throw err
    } finally {
      if (request === nodesRequest) isLoading.value = false
    }
  }

  /**
   * Refresh a single node from API
   */
  async function refreshNode(nodeId: string): Promise<SLMNode> {
    try {
      const node = await api.getNode(nodeId)
      nodes.value.set(node.node_id, node)

      // Update selected node if it matches
      if (selectedNode.value?.node_id === nodeId) {
        selectedNode.value = node
      }

      return node
    } catch (err) {
      error.value = errorText(err)
      throw err
    }
  }

  // ============================================================
  // Actions - Node Selection
  // ============================================================

  /**
   * Select a node for detail view
   */
  function selectNode(nodeId: string | null): void {
    if (nodeId === null) {
      selectedNode.value = null
      return
    }

    const node = nodes.value.get(nodeId)
    selectedNode.value = node || null
  }

  // ============================================================
  // Actions - Local State Updates
  // ============================================================

  /**
   * Update node in local state (no API call)
   */
  function setNodeLocal(node: SLMNode): void {
    nodes.value.set(node.node_id, node)
  }

  /**
   * Update node health in local state
   */
  function updateNodeHealth(nodeId: string, health: NodeHealth): void {
    const node = nodes.value.get(nodeId)
    if (node) {
      node.health = health
      node.status = health.status === 'healthy' ? 'online' :
                    health.status === 'degraded' ? 'degraded' :
                    health.status === 'unhealthy' ? 'error' : 'offline'
      nodes.value.set(nodeId, { ...node })
    }
  }

  /**
   * Update node status in local state
   */
  function updateNodeStatus(nodeId: string, status: string): void {
    const node = nodes.value.get(nodeId)
    if (node) {
      node.status = status as SLMNode['status']
      nodes.value.set(nodeId, { ...node })
    }
  }

  /**
   * Get node by ID from local state
   */
  function getNode(nodeId: string): SLMNode | undefined {
    return nodes.value.get(nodeId)
  }

  /**
   * Remove node from local state (no API call)
   */
  function removeNodeLocal(nodeId: string): void {
    nodes.value.delete(nodeId)

    // Clear selected if it was this node
    if (selectedNode.value?.node_id === nodeId) {
      selectedNode.value = null
    }

    // Clear cached data
    nodeEvents.value.delete(nodeId)
    certificateStatus.value.delete(nodeId)
    nodeUpdates.value.delete(nodeId)
  }

  // ============================================================
  // Actions - Node CRUD (API calls)
  // ============================================================

  /**
   * Register a new node
   */
  async function registerNode(data: NodeCreate): Promise<SLMNode> {
    try {
      const node = await api.registerNode(data)
      nodes.value.set(node.node_id, node)
      return node
    } catch (err) {
      error.value = errorText(err)
      throw err
    }
  }

  /**
   * Delete a node via API and remove from local state
   */
  async function deleteNode(nodeId: string): Promise<void> {
    try {
      await api.deleteNode(nodeId)
      removeNodeLocal(nodeId)
    } catch (err) {
      error.value = errorText(err)
      throw err
    }
  }

  /**
   * Update node details via API
   */
  async function updateNode(
    nodeId: string,
    data: NodeUpdate
  ): Promise<SLMNode> {
    try {
      const updatedNode = await api.updateNode(nodeId, data)
      nodes.value.set(updatedNode.node_id, updatedNode)

      // Update selected node if it matches
      if (selectedNode.value?.node_id === nodeId) {
        selectedNode.value = updatedNode
      }

      return updatedNode
    } catch (err) {
      error.value = errorText(err)
      throw err
    }
  }

  /**
   * Update node roles via API
   */
  async function updateNodeRoles(
    nodeId: string,
    roles: NodeRole[]
  ): Promise<SLMNode> {
    try {
      const updatedNode = await api.updateNodeRoles(nodeId, roles)
      nodes.value.set(updatedNode.node_id, updatedNode)

      // Update selected node if it matches
      if (selectedNode.value?.node_id === nodeId) {
        selectedNode.value = updatedNode
      }

      return updatedNode
    } catch (err) {
      error.value = errorText(err)
      throw err
    }
  }

  // ============================================================
  // Actions - Enrollment and Connection Testing
  // ============================================================

  /**
   * Start enrollment process for a node
   * Sets status to 'enrolling' optimistically
   */
  async function enrollNode(nodeId: string): Promise<void> {
    // Optimistic update
    updateNodeStatus(nodeId, 'enrolling')

    try {
      await api.enrollNode(nodeId)
      // Refresh to get actual status after enrollment starts
      await refreshNode(nodeId)
    } catch (err) {
      // Revert on failure - fetch fresh state
      await refreshNode(nodeId).catch(() => {
        // If refresh also fails, set to unhealthy
        updateNodeStatus(nodeId, 'unhealthy')
      })
      error.value = errorText(err)
      throw err
    }
  }

  /**
   * Test SSH connection to a node
   */
  async function testConnection(nodeId: string): Promise<ConnectionTestResult> {
    const node = nodes.value.get(nodeId)
    if (!node) {
      throw new Error(`Node ${nodeId} not found`)
    }

    try {
      const result = await api.testConnection({
        ip_address: node.ip_address,
        ssh_user: node.ssh_user || 'root',
        ssh_port: node.ssh_port || 22,
        auth_method: node.auth_method || 'password',
      })
      return result
    } catch (err) {
      error.value = errorText(err)
      throw err
    }
  }

  // ============================================================
  // Actions - Certificate Management
  // ============================================================

  /**
   * Get certificate status for a node
   */
  async function checkNodeCertificate(nodeId: string): Promise<CertificateInfo> {
    try {
      const certInfo = await api.getCertificateStatus(nodeId)
      certificateStatus.value.set(nodeId, certInfo)
      return certInfo
    } catch (err) {
      error.value = errorText(err)
      throw err
    }
  }

  /**
   * Renew certificate for a node
   */
  async function renewNodeCertificate(nodeId: string): Promise<void> {
    try {
      await api.renewCertificate(nodeId)
      // Refresh certificate status after renewal
      await checkNodeCertificate(nodeId)
    } catch (err) {
      error.value = errorText(err)
      throw err
    }
  }

  /**
   * Deploy certificate to a node (initial issuance)
   */
  async function deployNodeCertificate(nodeId: string): Promise<void> {
    try {
      await api.deployCertificate(nodeId)
      // Refresh certificate status after deployment
      await checkNodeCertificate(nodeId)
    } catch (err) {
      error.value = errorText(err)
      throw err
    }
  }

  // ============================================================
  // Actions - Events
  // ============================================================

  /**
   * Get lifecycle events for a node
   */
  async function getNodeEvents(
    nodeId: string,
    filters?: NodeEventFilters
  ): Promise<NodeEvent[]> {
    try {
      const events = await api.getNodeEvents(nodeId, filters)
      nodeEvents.value.set(nodeId, events)
      return events
    } catch (err) {
      error.value = errorText(err)
      throw err
    }
  }

  // ============================================================
  // Actions - Updates
  // ============================================================

  /**
   * Check for available updates for a node.
   *
   * Reconciles the cached fleet-wide update summary with this fresh scan
   * (#11964) so the node-card badge can never disagree with a live check.
   * Returns the full check response so callers get code_update_available/
   * code_status directly, even if this node has no cached summary entry yet.
   */
  async function checkNodeUpdates(nodeId: string): Promise<NodeUpdateCheckResponse> {
    try {
      const result = await api.checkUpdates(nodeId)
      nodeUpdates.value.set(nodeId, result.updates)
      reconcileNodeUpdateSummary(nodeId, result.total, result.code_update_available, result.code_status)
      return result
    } catch (err) {
      error.value = errorText(err)
      throw err
    }
  }

  /**
   * Apply updates to a node
   */
  async function applyNodeUpdates(
    nodeId: string,
    updateIds: string[]
  ): Promise<{ applied: string[]; failed: string[] }> {
    try {
      const result = await api.applyUpdates(nodeId, updateIds)

      // Refresh updates list after applying
      await checkNodeUpdates(nodeId)

      // Refresh node status
      await refreshNode(nodeId)

      return {
        applied: result.applied_updates,
        failed: result.failed_updates,
      }
    } catch (err) {
      error.value = errorText(err)
      throw err
    }
  }

  // ============================================================
  // Actions - NPU Management (Issue #255 - NPU Fleet Integration)
  // ============================================================

  /**
   * Fetch all NPU nodes with their status from the backend.
   * This is more efficient than fetching status individually.
   */
  async function fetchNpuNodes(): Promise<NPUNodeStatus[]> {
    try {
      const npuStatuses = await api.getNpuNodes()
      // Update cache with all NPU statuses
      npuCapabilities.value.clear()
      for (const status of npuStatuses) {
        npuCapabilities.value.set(status.node_id, status)
      }
      return npuStatuses
    } catch (err) {
      error.value = errorText(err)
      return []
    }
  }

  /**
   * Fetch NPU status for a specific node
   */
  async function fetchNpuStatus(nodeId: string): Promise<NPUNodeStatus> {
    try {
      const status = await api.getNpuStatus(nodeId)
      npuCapabilities.value.set(nodeId, status)
      return status
    } catch (err) {
      error.value = errorText(err)
      throw err
    }
  }

  /**
   * Fetch NPU status for all NPU nodes
   */
  async function fetchAllNpuStatus(): Promise<void> {
    const npuNodeList = npuNodes.value
    await Promise.all(
      npuNodeList.map(node => fetchNpuStatus(node.node_id))
    )
  }

  /**
   * Trigger NPU capability detection for a node.
   */
  async function triggerNpuDetection(nodeId: string, force: boolean = false): Promise<boolean> {
    try {
      const result = await api.triggerNpuDetection(nodeId, force)
      if (result.success && result.capabilities) {
        // Update cache if capabilities were returned immediately
        const existing = npuCapabilities.value.get(nodeId)
        if (existing) {
          npuCapabilities.value.set(nodeId, {
            ...existing,
            capabilities: result.capabilities,
            detectionStatus: 'detected',
          })
        }
      }
      return result.success
    } catch (err) {
      error.value = errorText(err)
      return false
    }
  }

  /**
   * Get cached NPU status for a node
   */
  function getNpuStatus(nodeId: string): NPUNodeStatus | undefined {
    return npuCapabilities.value.get(nodeId)
  }

  /**
   * Assign npu-worker role to a node and trigger capability detection.
   * Uses dedicated NPU API endpoint which handles role assignment and detection.
   */
  async function assignNpuRole(nodeId: string): Promise<SLMNode> {
    const node = nodes.value.get(nodeId)
    if (!node) {
      throw new Error(`Node ${nodeId} not found`)
    }

    try {
      // Use dedicated NPU API endpoint for proper role assignment and detection
      const result = await api.assignNpuRole(nodeId)
      if (!result.success) {
        throw new Error(result.message)
      }

      // Update local node state with the new role
      const updatedNode: SLMNode = {
        ...node,
        roles: [...node.roles, 'npu-worker'] as NodeRole[],
      }
      nodes.value.set(nodeId, updatedNode)

      // Fetch NPU status if detection was triggered
      if (result.detection_triggered) {
        await fetchNpuStatus(nodeId)
      }

      return updatedNode
    } catch (err) {
      error.value = errorText(err)
      throw err
    }
  }

  /**
   * Remove npu-worker role from a node.
   * Uses dedicated NPU API endpoint which cleans up NPU-specific data.
   */
  async function removeNpuRole(nodeId: string): Promise<SLMNode> {
    const node = nodes.value.get(nodeId)
    if (!node) {
      throw new Error(`Node ${nodeId} not found`)
    }

    try {
      // Use dedicated NPU API endpoint for proper cleanup
      const result = await api.removeNpuRole(nodeId)
      if (!result.success) {
        throw new Error(result.message)
      }

      // Update local node state to remove the role
      const updatedNode: SLMNode = {
        ...node,
        roles: node.roles.filter(r => r !== 'npu-worker') as NodeRole[],
      }
      nodes.value.set(nodeId, updatedNode)

      // Clear cached NPU data
      npuCapabilities.value.delete(nodeId)

      return updatedNode
    } catch (err) {
      error.value = errorText(err)
      throw err
    }
  }

  /**
   * Update NPU load balancing configuration
   */
  async function updateNpuLoadBalancing(
    config: NPULoadBalancingConfig
  ): Promise<void> {
    try {
      await api.updateNpuLoadBalancing(config)
      npuLoadBalancingConfig.value = config
    } catch (err) {
      error.value = errorText(err)
      throw err
    }
  }

  /**
   * Fetch current NPU load balancing configuration
   */
  async function fetchNpuLoadBalancing(): Promise<NPULoadBalancingConfig> {
    try {
      const config = await api.getNpuLoadBalancing()
      npuLoadBalancingConfig.value = config
      return config
    } catch (err) {
      error.value = errorText(err)
      throw err
    }
  }

  // Actions - NPU Metrics & Config (Issue #590)

  /** Cached fleet-level metrics */
  const npuFleetMetrics = ref<NPUFleetMetrics | null>(null)
  /** Per-node config cache */
  const npuWorkerConfigs = ref<Map<string, NPUWorkerConfig>>(new Map())

  async function fetchNpuFleetMetrics(): Promise<NPUFleetMetrics> {
    try {
      const metrics = await api.getNpuFleetMetrics()
      npuFleetMetrics.value = metrics
      return metrics
    } catch (err) {
      error.value = errorText(err)
      throw err
    }
  }

  async function fetchNpuNodeMetrics(
    nodeId: string
  ): Promise<NPUWorkerMetrics> {
    try {
      return await api.getNpuNodeMetrics(nodeId)
    } catch (err) {
      error.value = errorText(err)
      throw err
    }
  }

  async function fetchNpuWorkerConfig(
    nodeId: string
  ): Promise<NPUWorkerConfig> {
    try {
      const config = await api.getNpuWorkerConfig(nodeId)
      npuWorkerConfigs.value.set(nodeId, config)
      return config
    } catch (err) {
      error.value = errorText(err)
      throw err
    }
  }

  async function updateNpuWorkerConfig(
    nodeId: string,
    config: NPUWorkerConfig
  ): Promise<boolean> {
    try {
      const result = await api.updateNpuWorkerConfig(nodeId, config)
      if (result.success) {
        npuWorkerConfigs.value.set(nodeId, result.config)
      }
      return result.success
    } catch (err) {
      error.value = errorText(err)
      return false
    }
  }

  // ============================================================
  // Actions - Cache Management
  // ============================================================

  /**
   * Clear all cached data for a node
   */
  function clearNodeCache(nodeId: string): void {
    nodeEvents.value.delete(nodeId)
    certificateStatus.value.delete(nodeId)
    nodeUpdates.value.delete(nodeId)
    npuCapabilities.value.delete(nodeId)
  }

  /**
   * Clear all cached data
   */
  function clearAllCaches(): void {
    nodeEvents.value.clear()
    certificateStatus.value.clear()
    nodeUpdates.value.clear()
  }

  /**
   * Reset store to initial state
   */
  function $reset(): void {
    nodes.value.clear()
    isLoading.value = false
    error.value = nodesError.value = null
    nodesRequest++ // an in-flight read must not repopulate
    lastRefresh.value = null
    incomplete.value = null
    selectedNode.value = null
    clearAllCaches()
  }

  return {
    // State
    nodes,
    isLoading,
    error,
    lastRefresh,
    incomplete,
    nodesError,
    selectedNode,
    nodeEvents,
    certificateStatus,
    nodeUpdates,
    availableRoles,
    npuCapabilities,
    npuLoadBalancingConfig,
    fleetUpdateSummary,

    // Getters
    nodeList,
    fleetSummary,
    overallHealth,
    selectedNodeEvents,
    selectedNodeCertificate,
    npuNodes,
    nonNpuNodes,
    nodesNeedingUpdates,

    // Actions - Fleet Update Summary (#682)
    fetchFleetUpdateSummary,
    getNodeUpdateSummary,
    reconcileNodeUpdateSummary,

    // Actions - Roles
    fetchRoles,

    // Actions - Node Fetching
    fetchNodes,
    refreshNode,

    // Actions - Node Selection
    selectNode,

    // Actions - Local State Updates
    setNodeLocal,
    updateNodeHealth,
    updateNodeStatus,
    getNode,
    removeNodeLocal,

    // Actions - Node CRUD (API)
    registerNode,
    deleteNode,
    updateNode,
    updateNodeRoles,

    // Actions - Enrollment & Connection
    enrollNode,
    testConnection,

    // Actions - Certificate Management
    checkNodeCertificate,
    renewNodeCertificate,
    deployNodeCertificate,

    // Actions - Events
    getNodeEvents,

    // Actions - Updates
    checkNodeUpdates,
    applyNodeUpdates,

    // Actions - NPU Management
    fetchNpuNodes,
    fetchNpuStatus,
    fetchAllNpuStatus,
    triggerNpuDetection,
    getNpuStatus,
    assignNpuRole,
    removeNpuRole,
    updateNpuLoadBalancing,
    fetchNpuLoadBalancing,

    // Actions - NPU Metrics & Config (Issue #590)
    npuFleetMetrics,
    npuWorkerConfigs,
    fetchNpuFleetMetrics,
    fetchNpuNodeMetrics,
    fetchNpuWorkerConfig,
    updateNpuWorkerConfig,

    // Actions - Cache Management
    clearNodeCache,
    clearAllCaches,
    $reset,
  }
})
