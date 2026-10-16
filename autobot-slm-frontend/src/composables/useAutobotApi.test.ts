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
 * These tests exercise the REAL interceptors registered by `useAutobotApi` —
 * `axios.create` is stubbed with an instance that records the callbacks, which
 * are then invoked directly. They assert the three properties the raw-`fetch`
 * forks were losing (localStorage token fallback, 401 cleanup, 30s timeout),
 * plus the exact path and verb of every endpoint moved onto the client.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

const BACKEND = 'http://autobot.example/autobot-api'

type Headers = Record<string, unknown>
type RequestConfig = { headers: Headers }

const h = vi.hoisted(() => {
  const state = {
    createConfig: null as Record<string, unknown> | null,
    requestInterceptor: null as ((c: RequestConfig) => RequestConfig) | null,
    responseErrorInterceptor: null as ((e: unknown) => Promise<unknown>) | null,
    token: null as string | null,
  }
  const instance = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      // Plain functions, not vi.fn: the suite runs with `mockReset: true`,
      // which would strip a vi.fn implementation before the tests execute.
      request: {
        use: (fn: (c: RequestConfig) => RequestConfig) => {
          state.requestInterceptor = fn
        },
      },
      response: {
        use: (_ok: unknown, err: (e: unknown) => Promise<unknown>) => {
          state.responseErrorInterceptor = err
        },
      },
    },
  }
  return { state, instance }
})

vi.mock('axios', () => ({
  default: {
    create: (config: Record<string, unknown>) => {
      h.state.createConfig = config
      return h.instance
    },
  },
}))

vi.mock('@/config/ssot-config', () => ({ getBackendUrl: () => BACKEND }))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    get token() {
      return h.state.token
    },
  }),
}))

import { useAutobotApi, autobotApiErrorMessage } from './useAutobotApi'

/** Run the recorded request interceptor over a bare config. */
function applyRequestInterceptor(): Headers {
  useAutobotApi()
  const config: RequestConfig = { headers: {} }
  return h.state.requestInterceptor!(config).headers
}

function lastCall(fn: ReturnType<typeof vi.fn>): unknown[] {
  return fn.mock.calls[fn.mock.calls.length - 1] as unknown[]
}

describe('useAutobotApi transport contract (#13079)', () => {
  beforeEach(() => {
    h.state.token = null
    h.state.createConfig = null
    localStorage.clear()
    h.instance.get.mockResolvedValue({ data: {}, status: 200 })
    h.instance.post.mockResolvedValue({ data: {}, status: 200 })
    h.instance.put.mockResolvedValue({ data: {}, status: 200 })
    h.instance.patch.mockResolvedValue({ data: {}, status: 200 })
    h.instance.delete.mockResolvedValue({ data: {}, status: 200 })
  })

  it('resolves the base URL from getBackendUrl() and applies a 30s timeout', () => {
    useAutobotApi()

    expect(h.state.createConfig?.baseURL).toBe(BACKEND)
    expect(h.state.createConfig?.timeout).toBe(30000)
  })

  it('sends the SLM bearer token when the auth store holds one', () => {
    h.state.token = 'slm-token'

    expect(applyRequestInterceptor().Authorization).toBe('Bearer slm-token')
  })

  it('ignores a stray autobot_access_token: the SLM session token is the only bearer (#17856 row 8)', () => {
    // Nothing writes this key; the old fallback to it is gone.
    h.state.token = null
    localStorage.setItem('autobot_access_token', 'autobot-token')

    expect(applyRequestInterceptor().Authorization).toBeUndefined()
  })

  it('sends no Authorization header when neither token exists', () => {
    expect(applyRequestInterceptor().Authorization).toBeUndefined()
  })

  it('installs no response interceptor: the dead autobot_access_token 401 cleanup is gone (#17856 row 8)', () => {
    useAutobotApi()

    expect(h.state.responseErrorInterceptor).toBeNull()
  })
})

describe('useAutobotApi endpoints moved off raw fetch (#13079)', () => {
  beforeEach(() => {
    h.state.token = 'slm-token'
    localStorage.clear()
    h.instance.get.mockResolvedValue({ data: {}, status: 200 })
    h.instance.post.mockResolvedValue({ data: {}, status: 200 })
  })

  describe('agent org chart (#1405)', () => {
    it('GETs /agents/org', async () => {
      const tree = [{ agent_id: 'a1', name: 'A', org_role: 'manager' }]
      h.instance.get.mockResolvedValue({ data: tree, status: 200 })

      await expect(useAutobotApi().getAgentOrgTree()).resolves.toEqual(tree)
      expect(lastCall(h.instance.get)[0]).toBe('/agents/org')
    })

    it('GETs /agents/{id}/reports', async () => {
      await useAutobotApi().getAgentDirectReports('a1')

      expect(lastCall(h.instance.get)[0]).toBe('/agents/a1/reports')
    })

    it('GETs /agents/{id}/activity', async () => {
      await useAutobotApi().getAgentActivity('a1')

      expect(lastCall(h.instance.get)[0]).toBe('/agents/a1/activity')
    })

    it('GETs /agents/{id}/delegations with the role + limit query', async () => {
      h.instance.get.mockResolvedValue({ data: [], status: 200 })

      await useAutobotApi().getAgentDelegations('a1', { role: 'delegator', limit: 10 })

      expect(lastCall(h.instance.get)[0]).toBe('/agents/a1/delegations?role=delegator&limit=10')
    })

    it('POSTs the delegation body to /agents/{id}/delegate', async () => {
      const body = { assignee_id: 'a2', task_description: 'do it' }

      await useAutobotApi().delegateAgentTask('a1', body)

      expect(lastCall(h.instance.post).slice(0, 2)).toEqual(['/agents/a1/delegate', body])
    })
  })

  describe('agent processes (#1406)', () => {
    it('GETs /agents/{id}/processes with limit and status, unwrapping .processes', async () => {
      h.instance.get.mockResolvedValue({ data: { processes: [{ id: 'p1' }] }, status: 200 })

      const rows = await useAutobotApi().getAgentProcesses('a1', { limit: 50, status: 'running' })

      expect(lastCall(h.instance.get)[0]).toBe('/agents/a1/processes?limit=50&status=running')
      expect(rows).toEqual([{ id: 'p1' }])
    })

    it('omits the status filter when none is selected', async () => {
      h.instance.get.mockResolvedValue({ data: { processes: [] }, status: 200 })

      await useAutobotApi().getAgentProcesses('a1', { limit: 50, status: undefined })

      expect(lastCall(h.instance.get)[0]).toBe('/agents/a1/processes?limit=50')
    })

    it('requests the log body as text so axios does not JSON-parse it', async () => {
      h.instance.get.mockResolvedValue({ data: 'line one\nline two', status: 200 })

      const log = await useAutobotApi().getProcessLogs('p1')

      const [url, config] = lastCall(h.instance.get) as [string, { responseType: string }]
      expect(url).toBe('/processes/p1/logs')
      expect(config.responseType).toBe('text')
      expect(log).toBe('line one\nline two')
    })

    it('POSTs the signal name to /processes/{id}/signal', async () => {
      await useAutobotApi().signalProcess('p1', 'SIGKILL')

      expect(lastCall(h.instance.post).slice(0, 2)).toEqual([
        '/processes/p1/signal',
        { signal: 'SIGKILL' },
      ])
    })

    it('POSTs the spawn payload to /processes/spawn', async () => {
      const payload = { agent_id: 'a1', command: '/bin/true', args: ['-x'], timeout_seconds: 300 }

      await useAutobotApi().spawnProcess(payload)

      expect(lastCall(h.instance.post).slice(0, 2)).toEqual(['/processes/spawn', payload])
    })
  })

  describe('config revisions (#1404)', () => {
    it('GETs /config-revisions/{type}/{id} with the limit', async () => {
      h.instance.get.mockResolvedValue({ data: [], status: 200 })

      await useAutobotApi().getConfigRevisions('agent', 'orchestrator', 50)

      expect(lastCall(h.instance.get)[0]).toBe('/config-revisions/agent/orchestrator?limit=50')
    })

    it('POSTs the rollback path', async () => {
      await useAutobotApi().rollbackConfigRevision('agent', 'orchestrator', 'rev-9')

      expect(lastCall(h.instance.post)[0]).toBe(
        '/config-revisions/agent/orchestrator/rev-9/rollback',
      )
    })
  })

  describe('RBAC and cache admin', () => {
    it('GETs /settings/rbac/status', async () => {
      await useAutobotApi().getRbacStatus()

      expect(lastCall(h.instance.get)[0]).toBe('/settings/rbac/status')
    })

    it('POSTs the RBAC bootstrap body to /settings/rbac/initialize', async () => {
      const body = { create_admin: true, admin_username: 'ops' }

      await useAutobotApi().initializeRbac(body)

      expect(lastCall(h.instance.post).slice(0, 2)).toEqual(['/settings/rbac/initialize', body])
    })

    it('POSTs /cache/redis/clear/{database}', async () => {
      await useAutobotApi().clearRedisDatabase('sessions')

      expect(lastCall(h.instance.post)[0]).toBe('/cache/redis/clear/sessions')
    })
  })

  describe('health probe', () => {
    it('reports a 2xx backend as reachable', async () => {
      h.instance.get.mockResolvedValue({ data: {}, status: 200 })

      await expect(useAutobotApi().probeBackendHealth()).resolves.toEqual({ ok: true, status: 200 })
      expect(lastCall(h.instance.get)[0]).toBe('/health')
    })

    it('accepts every status so a 401 cannot log the operator out', async () => {
      h.instance.get.mockResolvedValue({ data: {}, status: 401 })

      const result = await useAutobotApi().probeBackendHealth()

      const [, config] = lastCall(h.instance.get) as [string, { validateStatus: (s: number) => boolean }]
      // validateStatus never rejects -> the response error interceptor that
      // removes `autobot_access_token` is never reached by the probe.
      expect(config.validateStatus(401)).toBe(true)
      expect(config.validateStatus(503)).toBe(true)
      expect(result).toEqual({ ok: false, status: 401 })
    })
  })
})

describe('autobotApiErrorMessage (#13079)', () => {
  it('surfaces the FastAPI detail string the raw fetch call sites showed', () => {
    const err = { response: { data: { detail: 'agent is not a manager' } } }

    expect(autobotApiErrorMessage(err, 'fallback')).toBe('agent is not a manager')
  })

  it('falls back to the Error message when there is no detail body', () => {
    expect(autobotApiErrorMessage(new Error('Network Error'), 'fallback')).toBe('Network Error')
  })

  it('falls back to the supplied default for a non-Error rejection', () => {
    expect(autobotApiErrorMessage('nope', 'Rollback failed')).toBe('Rollback failed')
  })
})
