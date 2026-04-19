// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2026 mrveiss
// Author: mrveiss
/**
 * Regression tests for #5200 — KnowledgeRepository connector-endpoint
 * response-shape handling.
 *
 * Backend returns wrapped pairs (`{config, status}` and `{connector_id, config}`)
 * that must be unpacked into the flat shapes callers declare.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { KnowledgeRepository } from '../KnowledgeRepository'
import type { ConnectorConfig, ConnectorStatus } from '@/types/connectors'

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api'
}))

function mkConfig(id: string, name = 'demo'): ConnectorConfig {
  return {
    connector_id: id,
    name,
    connector_type: 'file_server',
    enabled: true,
    target: '/data/test',
    verification_mode: 'none',
    schedule_cron: null,
    include_patterns: [],
    exclude_patterns: [],
    tier: 0,
    created_at: '2026-04-18T00:00:00Z',
    updated_at: '2026-04-18T00:00:00Z'
  } as unknown as ConnectorConfig
}

function mkStatus(connector_id: string): ConnectorStatus {
  return {
    connector_id,
    is_healthy: true,
    last_sync_at: null,
    last_sync_status: 'never',
    documents_count: 0
  } as unknown as ConnectorStatus
}

describe('KnowledgeRepository connector endpoints (#5200)', () => {
  let repo: KnowledgeRepository
  let getSpy: ReturnType<typeof vi.fn>
  let postSpy: ReturnType<typeof vi.fn>
  let putSpy: ReturnType<typeof vi.fn>

  beforeEach(() => {
    repo = new KnowledgeRepository()
    getSpy = vi.fn()
    postSpy = vi.fn()
    putSpy = vi.fn()
    // @ts-expect-error - override inherited methods for unit test isolation
    repo.get = getSpy
    // @ts-expect-error
    repo.post = postSpy
    // @ts-expect-error
    repo.put = putSpy
  })

  describe('listConnectors — unpacks {config, status} pairs', () => {
    it('splits backend-wrapped pairs into flat configs + statuses map', async () => {
      const cfg1 = mkConfig('id-1', 'first')
      const cfg2 = mkConfig('id-2', 'second')
      const st1 = mkStatus('id-1')
      const st2 = mkStatus('id-2')
      getSpy.mockResolvedValue({
        data: {
          connectors: [
            { config: cfg1, status: st1 },
            { config: cfg2, status: st2 }
          ],
          total: 2
        }
      })

      const result = await repo.listConnectors()

      expect(result.connectors).toHaveLength(2)
      expect(result.connectors[0]).toEqual(cfg1)
      expect(result.connectors[1]).toEqual(cfg2)
      expect(result.statuses).toEqual({ 'id-1': st1, 'id-2': st2 })
    })

    it('returns empty structures on empty backend response', async () => {
      getSpy.mockResolvedValue({ data: { connectors: [], total: 0 } })

      const result = await repo.listConnectors()

      expect(result.connectors).toEqual([])
      expect(result.statuses).toEqual({})
    })

    it('skips entries with missing config.connector_id', async () => {
      const cfg = mkConfig('id-1')
      const st = mkStatus('id-1')
      getSpy.mockResolvedValue({
        data: {
          connectors: [
            { config: cfg, status: st },
            // Malformed entry — no connector_id
            { config: {} as unknown as ConnectorConfig, status: st },
            // Missing status
            null as unknown as { config: ConnectorConfig; status: ConnectorStatus }
          ],
          total: 3
        }
      })

      const result = await repo.listConnectors()

      expect(result.connectors).toHaveLength(1)
      expect(result.connectors[0].connector_id).toBe('id-1')
      expect(result.statuses).toEqual({ 'id-1': st })
    })

    it('handles nullish data payload gracefully', async () => {
      getSpy.mockResolvedValue({ data: null })

      const result = await repo.listConnectors()

      expect(result.connectors).toEqual([])
      expect(result.statuses).toEqual({})
    })
  })

  describe('createConnector — extracts wrapped config', () => {
    it('unwraps {connector_id, config} response into flat ConnectorConfig', async () => {
      const cfg = mkConfig('new-id', 'created')
      postSpy.mockResolvedValue({
        data: { connector_id: 'new-id', config: cfg }
      })

      const result = await repo.createConnector({ name: 'created' })

      expect(result).toEqual(cfg)
      expect(postSpy).toHaveBeenCalledWith('/api/knowledge_base/connectors', {
        name: 'created'
      })
    })
  })

  describe('updateConnector — extracts wrapped config', () => {
    it('unwraps {connector_id, config} response into flat ConnectorConfig', async () => {
      const cfg = mkConfig('existing-id', 'updated')
      putSpy.mockResolvedValue({
        data: { connector_id: 'existing-id', config: cfg }
      })

      const result = await repo.updateConnector('existing-id', {
        name: 'updated'
      })

      expect(result).toEqual(cfg)
      expect(putSpy).toHaveBeenCalledWith(
        '/api/knowledge_base/connectors/existing-id',
        { name: 'updated' }
      )
    })
  })
})
