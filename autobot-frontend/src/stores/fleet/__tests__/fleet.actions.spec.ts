// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Fleet store (#19834): each slice's main path, and a failed read per slice. The adapter is a fake,
 * so these assert the store's own behaviour: what it caches, what it records on `error`, and what
 * it rethrows or swallows, as the SLM store did before the port.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { SLMNode } from '@autobot/slm-contract'

const api = vi.hoisted(() => {
  const names = [
    'getNodes', 'getNode', 'registerNode', 'updateNode', 'deleteNode', 'updateNodeRoles', 'enrollNode',
    'testConnection', 'getNodeEvents', 'getCertificateStatus', 'renewCertificate', 'deployCertificate',
    'getFleetUpdateSummary', 'checkUpdates', 'applyUpdates', 'getRoles', 'getNpuNodes', 'getNpuStatus',
    'triggerNpuDetection', 'assignNpuRole', 'removeNpuRole', 'getNpuLoadBalancing', 'updateNpuLoadBalancing',
    'getNpuFleetMetrics', 'getNpuNodeMetrics', 'getNpuWorkerConfig', 'updateNpuWorkerConfig',
  ]
  return Object.fromEntries(names.map((name) => [name, vi.fn()])) as Record<string, ReturnType<typeof vi.fn>>
})
vi.mock('@/utils/slmApi', () => ({ slmApi: api }))

import { useFleetStore } from '../index'

function node(id: string, extra: Partial<SLMNode> = {}): SLMNode {
  return {
    node_id: id,
    hostname: `${id}.local`,
    ip_address: '10.0.0.1',
    status: 'online',
    roles: [],
    health: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...extra,
  } as SLMNode
}

async function loaded(...nodes: SLMNode[]) {
  api.getNodes.mockResolvedValue(nodes)
  const store = useFleetStore()
  await store.fetchNodes()
  return store
}

describe('fleet store (#19834)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    Object.values(api).forEach((fn) => fn.mockReset())
  })

  it('exposes exactly the surface of the SLM fleet store it was ported from', () => {
    const surface = Object.keys(useFleetStore()).filter((key) => !key.startsWith('_') && (key === '$reset' || !key.startsWith('$')))
    expect(surface.sort()).toEqual([
      '$reset',
      'applyNodeUpdates',
      'assignNpuRole',
      'availableRoles',
      'certificateStatus',
      'checkNodeCertificate',
      'checkNodeUpdates',
      'clearAllCaches',
      'clearNodeCache',
      'deleteNode',
      'deployNodeCertificate',
      'enrollNode',
      'error',
      'fetchAllNpuStatus',
      'fetchFleetUpdateSummary',
      'fetchNodes',
      'fetchNpuFleetMetrics',
      'fetchNpuLoadBalancing',
      'fetchNpuNodeMetrics',
      'fetchNpuNodes',
      'fetchNpuStatus',
      'fetchNpuWorkerConfig',
      'fetchRoles',
      'fleetSummary',
      'fleetUpdateSummary',
      'getNode',
      'getNodeEvents',
      'getNodeUpdateSummary',
      'getNpuStatus',
      'isLoading',
      'lastRefresh',
      'nodeEvents',
      'nodeList',
      'nodeUpdates',
      'nodes',
      'nodesNeedingUpdates',
      'nonNpuNodes',
      'npuCapabilities',
      'npuFleetMetrics',
      'npuLoadBalancingConfig',
      'npuNodes',
      'npuWorkerConfigs',
      'overallHealth',
      'reconcileNodeUpdateSummary',
      'refreshNode',
      'registerNode',
      'removeNodeLocal',
      'removeNpuRole',
      'renewNodeCertificate',
      'selectNode',
      'selectedNode',
      'selectedNodeCertificate',
      'selectedNodeEvents',
      'setNodeLocal',
      'testConnection',
      'triggerNpuDetection',
      'updateNode',
      'updateNodeHealth',
      'updateNodeRoles',
      'updateNodeStatus',
      'updateNpuLoadBalancing',
      'updateNpuWorkerConfig',
    ])
  })

  describe('nodes slice', () => {
    it('fetchNodes replaces the node map and stamps lastRefresh', async () => {
      const store = await loaded(node('a'), node('b'))
      expect(store.nodeList.map((n) => n.node_id)).toEqual(['a', 'b'])
      expect(store.lastRefresh).toBeInstanceOf(Date)
      expect(store.isLoading).toBe(false)
      expect(store.error).toBeNull()
    })

    it('a failed fetchNodes records the message, rethrows, and clears isLoading', async () => {
      api.getNodes.mockRejectedValue(new Error('HTTP 503: revocation_check_unavailable'))
      const store = useFleetStore()
      await expect(store.fetchNodes()).rejects.toThrow('revocation_check_unavailable')
      expect(store.error).toBe('HTTP 503: revocation_check_unavailable')
      expect(store.isLoading).toBe(false)
      expect(store.nodeList).toEqual([])
    })

    it('a non-Error rejection records the fallback message', async () => {
      api.getNodes.mockRejectedValue('boom')
      const store = useFleetStore()
      await expect(store.fetchNodes()).rejects.toBe('boom')
      expect(store.error).toBe('Failed to fetch nodes')
    })

    it('refreshNode updates the map and the selected node', async () => {
      const store = await loaded(node('a'))
      store.selectNode('a')
      api.getNode.mockResolvedValue(node('a', { hostname: 'renamed' }))
      await store.refreshNode('a')
      expect(store.getNode('a')?.hostname).toBe('renamed')
      expect(store.selectedNode?.hostname).toBe('renamed')
    })

    it('a failed refreshNode records the node-specific message', async () => {
      const store = await loaded(node('a'))
      api.getNode.mockRejectedValue('nope')
      await expect(store.refreshNode('a')).rejects.toBe('nope')
      expect(store.error).toBe('Failed to refresh node a')
    })

    it('registerNode, updateNode and updateNodeRoles store the returned node', async () => {
      const store = await loaded(node('a'))
      api.registerNode.mockResolvedValue(node('b'))
      await store.registerNode({ hostname: 'b', ip_address: '10.0.0.2' })
      expect(store.getNode('b')).toBeDefined()
      api.updateNode.mockResolvedValue(node('a', { hostname: 'x' }))
      await store.updateNode('a', { hostname: 'x' })
      expect(store.getNode('a')?.hostname).toBe('x')
      api.updateNodeRoles.mockResolvedValue(node('a', { roles: ['redis'] }))
      await store.updateNodeRoles('a', ['redis'])
      expect(store.getNode('a')?.roles).toEqual(['redis'])
    })

    it('deleteNode drops the node, the selection and its caches', async () => {
      const store = await loaded(node('a'))
      store.selectNode('a')
      store.nodeEvents.set('a', [])
      api.deleteNode.mockResolvedValue(undefined)
      await store.deleteNode('a')
      expect(store.getNode('a')).toBeUndefined()
      expect(store.selectedNode).toBeNull()
      expect(store.nodeEvents.has('a')).toBe(false)
    })

    it('a failed deleteNode keeps the node', async () => {
      const store = await loaded(node('a'))
      api.deleteNode.mockRejectedValue(new Error('HTTP 403'))
      await expect(store.deleteNode('a')).rejects.toThrow('HTTP 403')
      expect(store.getNode('a')).toBeDefined()
      expect(store.error).toBe('HTTP 403')
    })

    it('updateNodeHealth moves the status with the health', async () => {
      const store = await loaded(node('a'))
      store.updateNodeHealth('a', { status: 'unhealthy' } as never)
      expect(store.getNode('a')?.status).toBe('error')
    })
  })

  describe('getters', () => {
    it('counts statuses, with pending/enrolling as offline, and derives overall health', async () => {
      const store = await loaded(
        node('a'),
        node('b', { status: 'degraded' }),
        node('c', { status: 'error' }),
        node('d', { status: 'pending' }),
        node('e', { status: 'enrolling' }),
      )
      expect(store.fleetSummary).toEqual({
        total_nodes: 5,
        healthy_nodes: 1,
        degraded_nodes: 1,
        unhealthy_nodes: 1,
        offline_nodes: 2,
      })
      expect(store.overallHealth).toBe('unhealthy')
    })

    it('is unknown with no nodes, degraded with only degraded ones, healthy when all online', async () => {
      const store = useFleetStore()
      expect(store.overallHealth).toBe('unknown')
      store.setNodeLocal(node('a', { status: 'degraded' }))
      expect(store.overallHealth).toBe('degraded')
      store.setNodeLocal(node('a'))
      expect(store.overallHealth).toBe('healthy')
    })

    it('splits NPU and non-NPU nodes', async () => {
      const store = await loaded(node('a', { roles: ['npu-worker'] }), node('b'))
      expect(store.npuNodes.map((n) => n.node_id)).toEqual(['a'])
      expect(store.nonNpuNodes.map((n) => n.node_id)).toEqual(['b'])
    })
  })

  describe('lifecycle slice', () => {
    it('enrollNode is optimistic, then re-reads the node', async () => {
      const store = await loaded(node('a'))
      api.enrollNode.mockResolvedValue({})
      api.getNode.mockResolvedValue(node('a', { status: 'online' }))
      const pending = store.enrollNode('a')
      expect(store.getNode('a')?.status).toBe('enrolling')
      await pending
      expect(store.getNode('a')?.status).toBe('online')
    })

    it('a failed enrollNode re-reads, and marks unhealthy when that fails too', async () => {
      const store = await loaded(node('a'))
      api.enrollNode.mockRejectedValue(new Error('HTTP 500'))
      api.getNode.mockRejectedValue(new Error('still down'))
      await expect(store.enrollNode('a')).rejects.toThrow('HTTP 500')
      expect(store.getNode('a')?.status).toBe('unhealthy')
      expect(store.error).toBe('HTTP 500')
    })

    it('testConnection sends the node address with SSH defaults, and refuses an unknown node', async () => {
      const store = await loaded(node('a'))
      api.testConnection.mockResolvedValue({ success: true })
      await expect(store.testConnection('a')).resolves.toEqual({ success: true })
      expect(api.testConnection).toHaveBeenCalledWith({
        ip_address: '10.0.0.1',
        ssh_user: 'root',
        ssh_port: 22,
        auth_method: 'password',
      })
      await expect(store.testConnection('missing')).rejects.toThrow('Node missing not found')
    })

    it('caches the certificate, and renew re-reads it', async () => {
      const store = await loaded(node('a'))
      store.selectNode('a')
      api.getCertificateStatus.mockResolvedValue({ cert_id: 'c1', status: 'valid' })
      await store.checkNodeCertificate('a')
      expect(store.selectedNodeCertificate).toEqual({ cert_id: 'c1', status: 'valid' })
      api.renewCertificate.mockResolvedValue({})
      api.getCertificateStatus.mockResolvedValue({ cert_id: 'c2', status: 'valid' })
      await store.renewNodeCertificate('a')
      expect(store.certificateStatus.get('a')).toEqual({ cert_id: 'c2', status: 'valid' })
    })

    it('a failed certificate read records the message and keeps the cache empty', async () => {
      const store = await loaded(node('a'))
      api.getCertificateStatus.mockRejectedValue('nope')
      await expect(store.checkNodeCertificate('a')).rejects.toBe('nope')
      expect(store.error).toBe('Failed to get certificate status for node a')
      expect(store.certificateStatus.size).toBe(0)
    })

    it('getNodeEvents caches by node and feeds selectedNodeEvents', async () => {
      const store = await loaded(node('a'))
      store.selectNode('a')
      api.getNodeEvents.mockResolvedValue([{ id: 'e1' }])
      await store.getNodeEvents('a', { limit: 5 })
      expect(api.getNodeEvents).toHaveBeenCalledWith('a', { limit: 5 })
      expect(store.selectedNodeEvents).toEqual([{ id: 'e1' }])
    })

    it('a failed events read rethrows with the node-specific message', async () => {
      const store = await loaded(node('a'))
      api.getNodeEvents.mockRejectedValue('nope')
      await expect(store.getNodeEvents('a')).rejects.toBe('nope')
      expect(store.error).toBe('Failed to get events for node a')
    })

    it('applyNodeUpdates re-checks updates and re-reads the node, returning applied/failed', async () => {
      const store = await loaded(node('a'))
      api.applyUpdates.mockResolvedValue({ applied_updates: ['u1'], failed_updates: ['u2'] })
      api.checkUpdates.mockResolvedValue({ updates: [], total: 0, code_update_available: false, code_status: 'up_to_date' })
      api.getNode.mockResolvedValue(node('a'))
      await expect(store.applyNodeUpdates('a', ['u1', 'u2'])).resolves.toEqual({ applied: ['u1'], failed: ['u2'] })
      expect(api.checkUpdates).toHaveBeenCalledWith('a')
      expect(api.getNode).toHaveBeenCalledWith('a')
    })

    it('fetchRoles stores the roles; a failure records and rethrows', async () => {
      const store = useFleetStore()
      api.getRoles.mockResolvedValue([{ name: 'redis' }])
      await store.fetchRoles()
      expect(store.availableRoles).toEqual([{ name: 'redis' }])
      api.getRoles.mockRejectedValue('nope')
      await expect(store.fetchRoles()).rejects.toBe('nope')
      expect(store.error).toBe('Failed to fetch roles')
    })
  })

  describe('NPU slice', () => {
    it('fetchNpuNodes replaces the cache; a failure yields [] and records the message', async () => {
      const store = useFleetStore()
      api.getNpuNodes.mockResolvedValue([{ node_id: 'a' }])
      await expect(store.fetchNpuNodes()).resolves.toEqual([{ node_id: 'a' }])
      expect(store.npuCapabilities.get('a')).toEqual({ node_id: 'a' })
      api.getNpuNodes.mockRejectedValue('nope')
      await expect(store.fetchNpuNodes()).resolves.toEqual([])
      expect(store.error).toBe('Failed to fetch NPU nodes')
    })

    it('fetchNpuStatus yields null on failure instead of throwing', async () => {
      const store = useFleetStore()
      api.getNpuStatus.mockRejectedValue('nope')
      await expect(store.fetchNpuStatus('a')).resolves.toBeNull()
      expect(store.error).toBe('Failed to fetch NPU status for node a')
    })

    it('assignNpuRole adds the role and fetches status when detection was triggered', async () => {
      const store = await loaded(node('a'))
      api.assignNpuRole.mockResolvedValue({ success: true, message: 'ok', node_id: 'a', detection_triggered: true })
      api.getNpuStatus.mockResolvedValue({ node_id: 'a' })
      const updated = await store.assignNpuRole('a')
      expect(updated.roles).toEqual(['npu-worker'])
      expect(store.getNpuStatus('a')).toEqual({ node_id: 'a' })
    })

    it('assignNpuRole throws the backend message when it reports failure', async () => {
      const store = await loaded(node('a'))
      api.assignNpuRole.mockResolvedValue({ success: false, message: 'no device', node_id: 'a' })
      await expect(store.assignNpuRole('a')).rejects.toThrow('no device')
      expect(store.error).toBe('no device')
      expect(store.getNode('a')?.roles).toEqual([])
    })

    it('removeNpuRole drops the role and the cached status', async () => {
      const store = await loaded(node('a', { roles: ['npu-worker'] }))
      store.npuCapabilities.set('a', { node_id: 'a' } as never)
      api.removeNpuRole.mockResolvedValue({ success: true, message: 'ok' })
      const updated = await store.removeNpuRole('a')
      expect(updated.roles).toEqual([])
      expect(store.getNpuStatus('a')).toBeUndefined()
    })

    it('triggerNpuDetection merges returned capabilities; a failure yields false', async () => {
      const store = useFleetStore()
      store.npuCapabilities.set('a', { node_id: 'a', detectionStatus: 'pending' } as never)
      api.triggerNpuDetection.mockResolvedValue({ success: true, capabilities: { deviceType: 'npu' } })
      await expect(store.triggerNpuDetection('a', true)).resolves.toBe(true)
      expect(store.getNpuStatus('a')).toMatchObject({ detectionStatus: 'detected', capabilities: { deviceType: 'npu' } })
      api.triggerNpuDetection.mockRejectedValue('nope')
      await expect(store.triggerNpuDetection('a')).resolves.toBe(false)
    })

    it('load balancing: update stores the config, a failed read yields null', async () => {
      const store = useFleetStore()
      api.updateNpuLoadBalancing.mockResolvedValue(undefined)
      await store.updateNpuLoadBalancing({ strategy: 'round-robin' } as never)
      expect(store.npuLoadBalancingConfig).toEqual({ strategy: 'round-robin' })
      api.getNpuLoadBalancing.mockRejectedValue('nope')
      await expect(store.fetchNpuLoadBalancing()).resolves.toBeNull()
    })

    it('metrics and worker config: main path and failed reads', async () => {
      const store = useFleetStore()
      api.getNpuFleetMetrics.mockResolvedValue({ total_nodes: 1 })
      await store.fetchNpuFleetMetrics()
      expect(store.npuFleetMetrics).toEqual({ total_nodes: 1 })
      api.getNpuWorkerConfig.mockResolvedValue({ failure_action: 'retry' })
      await store.fetchNpuWorkerConfig('a')
      expect(store.npuWorkerConfigs.get('a')).toEqual({ failure_action: 'retry' })
      api.updateNpuWorkerConfig.mockResolvedValue({ success: true, message: 'ok', config: { failure_action: 'skip' } })
      await expect(store.updateNpuWorkerConfig('a', { failure_action: 'skip' } as never)).resolves.toBe(true)
      expect(store.npuWorkerConfigs.get('a')).toEqual({ failure_action: 'skip' })
      api.getNpuNodeMetrics.mockRejectedValue('nope')
      await expect(store.fetchNpuNodeMetrics('a')).resolves.toBeNull()
      expect(store.error).toBe('Failed to fetch metrics for node a')
    })
  })

  describe('cache slice', () => {
    it('clearNodeCache clears one node; $reset clears the node list and the three caches only', async () => {
      const store = await loaded(node('a'))
      store.selectNode('a')
      store.nodeEvents.set('a', [])
      store.certificateStatus.set('a', {} as never)
      store.nodeUpdates.set('a', [])
      store.npuCapabilities.set('a', {} as never)
      store.clearNodeCache('a')
      expect(store.npuCapabilities.has('a')).toBe(false)
      expect(store.nodeEvents.has('a')).toBe(false)

      store.npuCapabilities.set('a', {} as never)
      store.availableRoles = [{ name: 'redis' } as never]
      store.$reset()
      expect(store.nodeList).toEqual([])
      expect(store.selectedNode).toBeNull()
      expect(store.lastRefresh).toBeNull()
      // As in the SLM store, $reset leaves roles and NPU state alone.
      expect(store.availableRoles).toHaveLength(1)
      expect(store.npuCapabilities.has('a')).toBe(true)
    })
  })
})
