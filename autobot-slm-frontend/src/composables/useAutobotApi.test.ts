// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #13079 — the transport contract seven SLM components used to re-implement.
 *
 * OrgChartTab, ProcessMonitorTab, ConfigHistoryTab, RedisServicePanel,
 * UserManagementSettings, CacheSettings and BackendSettings each built their
 * own `fetch` against `getBackendUrl()` that sent only
 * `Bearer ${authStore.token}`. With an autobot-issued token and no SLM token
 * those views 401'd while every tool on this client worked (proven in #13077
 * for AdvancedControlTool).
 *
 * The client is the SLM's own `SlmApiClient` pointed at the main backend (#12363), so the
 * bearer token, the 401 session handling, the timeout and `HttpError` are tested once in
 * `utils/ApiClient.test.ts`. These tests pin what this file adds: the base URL, and the exact
 * path and verb of every endpoint moved onto the client.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { HttpError } from '@autobot/ui'
import { backendClient } from '@/testing/mockAutobotBackendClient'

const BACKEND = 'http://autobot.example/autobot-api'

vi.mock('@/utils/ApiClient', async (importOriginal) =>
  (await import('@/testing/mockAutobotBackendClient')).withMockedBackendClient(importOriginal),
)
vi.mock('@/config/ssot-config', () => ({
  getBackendUrl: () => BACKEND,
  getEnvPositiveInt: (_key: string, fallback: number) => fallback,
}))

import { useAutobotApi, autobotApiErrorMessage } from './useAutobotApi'

function lastCall(fn: ReturnType<typeof vi.fn>): unknown[] {
  return fn.mock.calls[fn.mock.calls.length - 1] as unknown[]
}

describe('useAutobotApi transport (#12363)', () => {
  it('points an SlmApiClient at getBackendUrl()', () => {
    backendClient.baseUrl = null
    useAutobotApi()

    expect(backendClient.baseUrl).toBe(BACKEND)
  })

  it('surfaces a main-backend 401 instead of logging out until #10193', () => {
    backendClient.keepSessionOn401 = null
    useAutobotApi()

    expect(backendClient.keepSessionOn401).toBe(true)
  })
})

describe('useAutobotApi endpoints moved off raw fetch (#13079)', () => {
  beforeEach(() => {
    Object.values(backendClient).forEach((m) => typeof m === 'function' && (m as ReturnType<typeof vi.fn>).mockReset())
    backendClient.get.mockResolvedValue({})
    backendClient.post.mockResolvedValue({})
  })

  describe('agent org chart (#1405)', () => {
    it('GETs /agents/org', async () => {
      const tree = [{ agent_id: 'a1', name: 'A', org_role: 'manager' }]
      backendClient.get.mockResolvedValue(tree)

      await expect(useAutobotApi().getAgentOrgTree()).resolves.toEqual(tree)
      expect(lastCall(backendClient.get)[0]).toBe('/agents/org')
    })

    it('GETs /agents/{id}/reports', async () => {
      await useAutobotApi().getAgentDirectReports('a1')

      expect(lastCall(backendClient.get)[0]).toBe('/agents/a1/reports')
    })

    it('GETs /agents/{id}/activity', async () => {
      await useAutobotApi().getAgentActivity('a1')

      expect(lastCall(backendClient.get)[0]).toBe('/agents/a1/activity')
    })

    it('GETs /agents/{id}/delegations with the role + limit query', async () => {
      backendClient.get.mockResolvedValue([])

      await useAutobotApi().getAgentDelegations('a1', { role: 'delegator', limit: 10 })

      expect(lastCall(backendClient.get)[0]).toBe('/agents/a1/delegations?role=delegator&limit=10')
    })

    it('POSTs the delegation body to /agents/{id}/delegate', async () => {
      const body = { assignee_id: 'a2', task_description: 'do it' }

      await useAutobotApi().delegateAgentTask('a1', body)

      expect(lastCall(backendClient.post).slice(0, 2)).toEqual(['/agents/a1/delegate', body])
    })
  })

  describe('agent processes (#1406)', () => {
    it('GETs /agents/{id}/processes with limit and status, unwrapping .processes', async () => {
      backendClient.get.mockResolvedValue({ processes: [{ id: 'p1' }] })

      const rows = await useAutobotApi().getAgentProcesses('a1', { limit: 50, status: 'running' })

      expect(lastCall(backendClient.get)[0]).toBe('/agents/a1/processes?limit=50&status=running')
      expect(rows).toEqual([{ id: 'p1' }])
    })

    it('omits the status filter when none is selected', async () => {
      backendClient.get.mockResolvedValue({ processes: [] })

      await useAutobotApi().getAgentProcesses('a1', { limit: 50, status: undefined })

      expect(lastCall(backendClient.get)[0]).toBe('/agents/a1/processes?limit=50')
    })

    it('requests the log body as text so the client does not JSON-parse it', async () => {
      backendClient.get.mockResolvedValue('line one\nline two')

      const log = await useAutobotApi().getProcessLogs('p1')

      const [url, config] = lastCall(backendClient.get) as [string, { responseType: string }]
      expect(url).toBe('/processes/p1/logs')
      expect(config.responseType).toBe('text')
      expect(log).toBe('line one\nline two')
    })

    it('POSTs the signal name to /processes/{id}/signal', async () => {
      await useAutobotApi().signalProcess('p1', 'SIGKILL')

      expect(lastCall(backendClient.post).slice(0, 2)).toEqual([
        '/processes/p1/signal',
        { signal: 'SIGKILL' },
      ])
    })

    it('POSTs the spawn payload to /processes/spawn', async () => {
      const payload = { agent_id: 'a1', command: '/bin/true', args: ['-x'], timeout_seconds: 300 }

      await useAutobotApi().spawnProcess(payload)

      expect(lastCall(backendClient.post).slice(0, 2)).toEqual(['/processes/spawn', payload])
    })
  })

  describe('config revisions (#1404)', () => {
    it('GETs /config-revisions/{type}/{id} with the limit', async () => {
      backendClient.get.mockResolvedValue([])

      await useAutobotApi().getConfigRevisions('agent', 'orchestrator', 50)

      expect(lastCall(backendClient.get)[0]).toBe('/config-revisions/agent/orchestrator?limit=50')
    })

    it('POSTs the rollback path', async () => {
      await useAutobotApi().rollbackConfigRevision('agent', 'orchestrator', 'rev-9')

      expect(lastCall(backendClient.post)[0]).toBe(
        '/config-revisions/agent/orchestrator/rev-9/rollback',
      )
    })
  })

  describe('RBAC and cache admin', () => {
    it('GETs /settings/rbac/status', async () => {
      await useAutobotApi().getRbacStatus()

      expect(lastCall(backendClient.get)[0]).toBe('/settings/rbac/status')
    })

    it('POSTs the RBAC bootstrap body to /settings/rbac/initialize', async () => {
      const body = { create_admin: true, admin_username: 'ops' }

      await useAutobotApi().initializeRbac(body)

      expect(lastCall(backendClient.post).slice(0, 2)).toEqual(['/settings/rbac/initialize', body])
    })

    it('POSTs /cache/redis/clear/{database}', async () => {
      await useAutobotApi().clearRedisDatabase('sessions')

      expect(lastCall(backendClient.post)[0]).toBe('/cache/redis/clear/sessions')
    })
  })

  describe('health probe', () => {
    it('reports a 2xx backend as reachable', async () => {
      backendClient.rawRequest.mockResolvedValue({ ok: true, status: 200 })

      await expect(useAutobotApi().probeBackendHealth()).resolves.toEqual({ ok: true, status: 200 })
      expect(lastCall(backendClient.rawRequest)[0]).toBe('/health')
    })

    it('reports a 401 instead of throwing, and keeps the session (#12363)', async () => {
      backendClient.rawRequest.mockResolvedValue({ ok: false, status: 401 })

      const result = await useAutobotApi().probeBackendHealth()

      expect(lastCall(backendClient.rawRequest)[1]).toEqual({ keepSessionOn401: true })
      expect(result).toEqual({ ok: false, status: 401 })
    })
  })
})

describe('autobotApiErrorMessage (#13079)', () => {
  it('surfaces the FastAPI detail string the raw fetch call sites showed', () => {
    const err = new HttpError(400, 'Bad Request', { detail: 'agent is not a manager' })

    expect(autobotApiErrorMessage(err, 'fallback')).toBe('agent is not a manager')
  })

  it('leads with the caller fallback for a network error, keeping the cause', () => {
    expect(autobotApiErrorMessage(new Error('Network Error'), 'fallback')).toBe('fallback: Network Error')
  })

  it('leads with the caller fallback and the status for an HttpError without a detail', () => {
    expect(autobotApiErrorMessage(new HttpError(500, 'Internal Server Error'), 'Navigation failed')).toBe(
      'Navigation failed (HTTP 500)',
    )
  })

  it('falls back to the supplied default for a non-Error rejection', () => {
    expect(autobotApiErrorMessage('nope', 'Rollback failed')).toBe('Rollback failed')
  })
})
