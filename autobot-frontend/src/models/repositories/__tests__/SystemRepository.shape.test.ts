// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2026 mrveiss
// Author: mrveiss
/**
 * Regression tests for #5207 audit — SystemRepository response-shape handling.
 *
 * Backend endpoints return envelope-wrapped payloads that must be unpacked
 * into the flat shapes callers declare.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SystemRepository } from '../SystemRepository'

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api'
}))

describe('SystemRepository shape handling (#5207 audit)', () => {
  let repo: SystemRepository
  let getSpy: ReturnType<typeof vi.fn>

  beforeEach(() => {
    repo = new SystemRepository()
    getSpy = vi.fn()
    // @ts-expect-error - override inherited methods for unit test isolation
    repo.get = getSpy
  })

  describe('getTerminalHistory — unwraps backend `sessions` list', () => {
    it('unwraps `sessions` from {status, total, sessions}', async () => {
      const sessions = [
        { success: true, exit_code: 0, stdout: 'ok', stderr: '',
          execution_time: 0.1, command: 'ls' }
      ]
      getSpy.mockResolvedValue({
        data: { status: 'success', total: 1, sessions }
      })

      const result = await repo.getTerminalHistory()

      expect(result).toEqual(sessions)
      expect(Array.isArray(result)).toBe(true)
    })

    it('returns [] on missing sessions field', async () => {
      getSpy.mockResolvedValue({ data: { status: 'success', total: 0 } })

      const result = await repo.getTerminalHistory()

      expect(result).toEqual([])
    })

    it('returns [] on nullish payload', async () => {
      getSpy.mockResolvedValue({ data: null })

      const result = await repo.getTerminalHistory()

      expect(result).toEqual([])
    })
  })

  describe('getLogs — unwraps backend `entries` list', () => {
    it('unwraps `entries` from {entries, count, limit, source}', async () => {
      const entries = [
        { raw: '...', service: 'backend', timestamp: 't',
          level: 'INFO', message: 'started', source_type: 'file' }
      ]
      getSpy.mockResolvedValue({
        data: { entries, count: 1, limit: 100, source: 'file' }
      })

      const result = await repo.getLogs()

      expect(result).toEqual(entries)
      expect(Array.isArray(result)).toBe(true)
    })

    it('appends query params when level and limit supplied', async () => {
      getSpy.mockResolvedValue({ data: { entries: [] } })

      await repo.getLogs('ERROR', 50)

      expect(getSpy).toHaveBeenCalledWith(
        expect.stringContaining('level=ERROR')
      )
      expect(getSpy).toHaveBeenCalledWith(
        expect.stringContaining('limit=50')
      )
    })

    it('returns [] on missing entries field', async () => {
      getSpy.mockResolvedValue({ data: { count: 0 } })

      const result = await repo.getLogs()

      expect(result).toEqual([])
    })
  })
})
