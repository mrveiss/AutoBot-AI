// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2026 mrveiss
// Author: mrveiss
/**
 * Regression tests for #5207 audit — SystemRepository response-shape handling.
 *
 * Backend endpoints return envelope-wrapped payloads that must be unpacked
 * into the flat shapes callers declare.
 *
 * Extended in #5212 to cover checkHealth / getSystemInfo / getSystemMetrics,
 * whose declared types were fabricated (fields that never existed on the
 * backend payload) before this fix.
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

  // ==========================================================================
  // #5212: checkHealth / getSystemInfo / getSystemMetrics
  // ==========================================================================

  describe('checkHealth — unwraps /api/system/health (#5212)', () => {
    it('unwraps {status, timestamp, initialization, components} from backend', async () => {
      const payload = {
        status: 'healthy',
        timestamp: '2026-04-20T09:20:06.896132+00:00',
        initialization: { status: 'ready', message: 'All services initialized' },
        components: {
          backend: 'healthy',
          config: 'healthy',
          logging: 'healthy',
          conversation_files_db: 'healthy'
        }
      }
      getSpy.mockResolvedValue({ data: payload })

      const result = await repo.checkHealth()

      expect(result.status).toBe('healthy')
      expect(result.timestamp).toBe(payload.timestamp)
      expect(result.initialization).toEqual(payload.initialization)
      expect(result.components).toEqual(payload.components)
    })

    it("defaults status to 'unknown' and components to {} on nullish payload", async () => {
      getSpy.mockResolvedValue({ data: null })

      const result = await repo.checkHealth()

      expect(result.status).toBe('unknown')
      expect(result.components).toEqual({})
      expect(result.timestamp).toBeUndefined()
      expect(result.initialization).toBeUndefined()
    })

    it('tolerates malformed payload (missing components)', async () => {
      getSpy.mockResolvedValue({ data: { status: 'degraded' } })

      const result = await repo.checkHealth()

      expect(result.status).toBe('degraded')
      expect(result.components).toEqual({})
    })

    it('hits the /system/health endpoint', async () => {
      getSpy.mockResolvedValue({ data: { status: 'healthy' } })

      await repo.checkHealth()

      expect(getSpy).toHaveBeenCalledWith('/api/system/health')
    })
  })

  describe('getSystemInfo — unwraps /api/system/info (#5212)', () => {
    it('unwraps {name, version, python_version, timestamp, features} from backend', async () => {
      const payload = {
        name: 'AutoBot Backend',
        version: '1.0.0',
        python_version: '3.12.13',
        timestamp: '2026-04-20T09:20:07.466719+00:00',
        features: {
          llm_integration: true,
          knowledge_base: true,
          chat_system: true,
          caching: true,
          websockets: true
        }
      }
      getSpy.mockResolvedValue({ data: payload })

      const result = await repo.getSystemInfo()

      expect(result).toEqual(payload)
    })

    it("defaults string fields to 'unknown' and features to {} on nullish payload", async () => {
      getSpy.mockResolvedValue({ data: null })

      const result = await repo.getSystemInfo()

      expect(result.name).toBe('unknown')
      expect(result.version).toBe('unknown')
      expect(result.python_version).toBe('unknown')
      expect(result.features).toEqual({})
    })

    it('tolerates partial payload (missing features)', async () => {
      getSpy.mockResolvedValue({
        data: { name: 'AutoBot', version: '1.0.0', python_version: '3.12' }
      })

      const result = await repo.getSystemInfo()

      expect(result.name).toBe('AutoBot')
      expect(result.features).toEqual({})
    })
  })

  describe('getSystemStatus — aliases getSystemInfo (#5212)', () => {
    it('hits /system/info just like getSystemInfo', async () => {
      getSpy.mockResolvedValue({
        data: { name: 'AutoBot', version: '1.0.0', python_version: '3.12' }
      })

      const result = await repo.getSystemStatus()

      expect(getSpy).toHaveBeenCalledWith('/api/system/info')
      expect(result.name).toBe('AutoBot')
    })
  })

  describe('getSystemMetrics — unwraps /api/system/metrics (#5212)', () => {
    it('unwraps nested {timestamp, system: {cpu_percent, memory, disk}, python, cache} from backend', async () => {
      const payload = {
        timestamp: '2026-04-20T09:20:08.933609+00:00',
        system: {
          cpu_percent: 11.1,
          memory: {
            total: 63198334976,
            available: 51172343808,
            percent: 19.0,
            used: 12025991168,
            free: 49076850688
          },
          disk: {
            total: 1081101176832,
            used: 126288633856,
            free: 899820187648,
            percent: 11.681481489648299
          }
        },
        python: {
          version: '3.12.13',
          executable: '/opt/autobot/autobot-backend/venv/bin/python3.12'
        },
        cache: {
          status: 'enabled',
          total_keys: 0,
          memory_usage: '76.78M',
          default_ttl: 300
        }
      }
      getSpy.mockResolvedValue({ data: payload })

      const result = await repo.getSystemMetrics()

      expect(result.timestamp).toBe(payload.timestamp)
      expect(result.system.cpu_percent).toBe(11.1)
      expect(result.system.memory.percent).toBe(19.0)
      expect(result.system.disk.percent).toBeCloseTo(11.68, 1)
      expect(result.python).toEqual(payload.python)
      expect(result.cache).toEqual(payload.cache)
    })

    it('defaults all nested numeric fields to 0 on nullish payload', async () => {
      getSpy.mockResolvedValue({ data: null })

      const result = await repo.getSystemMetrics()

      expect(result.timestamp).toBe('')
      expect(result.system.cpu_percent).toBe(0)
      expect(result.system.memory.total).toBe(0)
      expect(result.system.memory.available).toBe(0)
      expect(result.system.memory.percent).toBe(0)
      expect(result.system.memory.used).toBe(0)
      expect(result.system.memory.free).toBe(0)
      expect(result.system.disk.total).toBe(0)
      expect(result.system.disk.used).toBe(0)
      expect(result.system.disk.free).toBe(0)
      expect(result.system.disk.percent).toBe(0)
      expect(result.python).toBeUndefined()
      expect(result.cache).toBeUndefined()
    })

    it('tolerates partial payload (missing python/cache)', async () => {
      getSpy.mockResolvedValue({
        data: {
          timestamp: 't',
          system: {
            cpu_percent: 5,
            memory: { total: 1, available: 1, percent: 1, used: 0, free: 1 },
            disk: { total: 1, used: 0, free: 1, percent: 0 }
          }
        }
      })

      const result = await repo.getSystemMetrics()

      expect(result.system.cpu_percent).toBe(5)
      expect(result.python).toBeUndefined()
      expect(result.cache).toBeUndefined()
    })

    it('tolerates partial nested objects (missing system.memory)', async () => {
      getSpy.mockResolvedValue({
        data: {
          timestamp: 't',
          system: { cpu_percent: 7 }
        }
      })

      const result = await repo.getSystemMetrics()

      expect(result.system.cpu_percent).toBe(7)
      expect(result.system.memory.total).toBe(0)
      expect(result.system.disk.total).toBe(0)
    })
  })
})
