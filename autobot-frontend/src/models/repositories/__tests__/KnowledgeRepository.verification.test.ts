// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Regression tests for #5207 audit — KnowledgeRepository verification and
 * connector history/sync/test response-shape handling.
 *
 * Backend returns envelope-wrapped payloads that must be unpacked into
 * the flat shapes callers declare (same class-of-bug as #5200).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { KnowledgeRepository } from '../KnowledgeRepository'

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api'
}))

describe('KnowledgeRepository verification endpoints (#5207 audit)', () => {
  let repo: KnowledgeRepository
  let getSpy: ReturnType<typeof vi.fn>
  let postSpy: ReturnType<typeof vi.fn>

  beforeEach(() => {
    repo = new KnowledgeRepository()
    getSpy = vi.fn()
    postSpy = vi.fn()
    // @ts-expect-error - override inherited methods for unit test isolation
    repo.get = getSpy
    // @ts-expect-error - override inherited methods for unit test isolation
    repo.post = postSpy
  })

  describe('getPendingVerifications — unwraps backend `pending` list', () => {
    it('unwraps `pending` from {status, pending, total, limit, offset, has_more}', async () => {
      const sources = [
        { fact_id: 'f1', content: 'x', source_type: 's', quality_score: 0.9,
          timestamp: 't', domain: null, title: null, url: null }
      ]
      getSpy.mockResolvedValue({
        data: {
          status: 'success',
          pending: sources,
          total: 1,
          limit: 20,
          offset: 0,
          has_more: false
        }
      })

      const result = await repo.getPendingVerifications(1, 20)

      expect(result.sources).toEqual(sources)
      expect(result.total).toBe(1)
      expect(result.page).toBe(1)
    })

    it('maps page=1 to offset=0 and page=3/pageSize=10 to offset=20', async () => {
      getSpy.mockResolvedValue({
        data: { status: 'success', pending: [], total: 0 }
      })

      await repo.getPendingVerifications(3, 10)

      expect(getSpy).toHaveBeenCalledWith(
        '/api/knowledge_base/verification/pending?limit=10&offset=20',
        { skipCache: true }
      )
    })

    it('returns safe defaults on missing/nullish payload', async () => {
      getSpy.mockResolvedValue({ data: null })

      const result = await repo.getPendingVerifications()

      expect(result).toEqual({ sources: [], total: 0, page: 1 })
    })
  })

  describe('getVerificationConfig — unwraps backend `config` envelope', () => {
    it('unwraps `config` from {status, config}', async () => {
      const cfg = { mode: 'collaborative' as const, quality_threshold: 0.75 }
      getSpy.mockResolvedValue({
        data: { status: 'success', config: cfg }
      })

      const result = await repo.getVerificationConfig()

      expect(result).toEqual(cfg)
    })
  })

  describe('testConnector — normalises {connector_id, healthy} to {success, message}', () => {
    it('returns success=true with friendly message when healthy', async () => {
      postSpy.mockResolvedValue({
        data: { connector_id: 'c1', healthy: true }
      })

      const result = await repo.testConnector('c1')

      expect(result.success).toBe(true)
      expect(result.message).toMatch(/OK/i)
    })

    it('returns success=false when unhealthy', async () => {
      postSpy.mockResolvedValue({
        data: { connector_id: 'c1', healthy: false }
      })

      const result = await repo.testConnector('c1')

      expect(result.success).toBe(false)
      expect(result.message).toMatch(/failed/i)
    })

    it('treats missing payload as unhealthy', async () => {
      postSpy.mockResolvedValue({ data: null })

      const result = await repo.testConnector('c1')

      expect(result.success).toBe(false)
    })
  })

  describe('syncConnector — returns trigger ack, not completed SyncResult', () => {
    it('passes through {connector_id, status, incremental}', async () => {
      postSpy.mockResolvedValue({
        data: { connector_id: 'c1', status: 'sync_started', incremental: true }
      })

      const result = await repo.syncConnector('c1', true)

      expect(result).toEqual({
        connector_id: 'c1',
        status: 'sync_started',
        incremental: true
      })
    })

    it('falls back to input id + incremental when backend omits fields', async () => {
      postSpy.mockResolvedValue({ data: {} })

      const result = await repo.syncConnector('my-id', false)

      expect(result.connector_id).toBe('my-id')
      expect(result.incremental).toBe(false)
      expect(result.status).toBe('unknown')
    })
  })

  describe('getConnectorHistory — unwraps backend `history` list', () => {
    it('unwraps `history` from {connector_id, history, total}', async () => {
      const entries = [
        { connector_id: 'c1', started_at: '2026-04-18T00:00:00Z',
          completed_at: '2026-04-18T00:00:01Z', status: 'success' as const,
          added: 5, updated: 2, deleted: 0, errors: [] }
      ]
      getSpy.mockResolvedValue({
        data: { connector_id: 'c1', history: entries, total: 1 }
      })

      const result = await repo.getConnectorHistory('c1', 20)

      expect(result).toEqual(entries)
      expect(Array.isArray(result)).toBe(true)
    })

    it('returns [] on missing history field', async () => {
      getSpy.mockResolvedValue({ data: { connector_id: 'c1', total: 0 } })

      const result = await repo.getConnectorHistory('c1')

      expect(result).toEqual([])
    })
  })
})
