// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #13079 — useSkills / useSkillGovernance migrated off their two private
 * `axios.create` instances onto `useAutobotApi`.
 *
 * `useSkills` owned `axios.create({ baseURL: getBackendUrl() + '/skills/',
 * timeout: 15000 })` and `useSkillGovernance` a second, bare
 * `axios.create({ timeout: 15000 })`. Both attached only
 * `Bearer ${authStore.token}` — no `autobot_access_token` fallback, no 401
 * cleanup — which is exactly the fork that made `AdvancedControlTool` 401 while
 * its ~17 siblings worked (#13077).
 *
 * The harness stubs `axios.create` and records the interceptors `useAutobotApi`
 * registers, then invokes them directly, so these assert the REAL transport
 * behaviour (header actually attached, 401 actually clearing storage, the
 * timeout actually configured) rather than that a function was called.
 *
 * Which tests prove a defect and which are regression guards is stated per
 * `describe` block below.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

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

import { useSkills, useSkillGovernance } from './useSkills'
import { SKILL_APPROVAL_POLL_TIMEOUT_MS } from '@/constants/api-timeouts'

/** The single axios instance every call in this module now shares. */
function calls(verb: 'get' | 'post' | 'put') {
  return h.instance[verb].mock.calls as unknown[][]
}

function firstUrl(verb: 'get' | 'post' | 'put'): string {
  return calls(verb)[0]?.[0] as string
}

/** An axios-shaped rejection carrying a FastAPI `{ detail }` body. */
function detailError(status: number, detail: string) {
  const err = new Error(`Request failed with status code ${status}`) as Error & {
    response: { status: number; data: { detail: string } }
  }
  err.response = { status, data: { detail } }
  return err
}

describe('useSkills — migrated onto useAutobotApi (#13079)', () => {
  beforeEach(() => {
    h.state.token = null
    h.state.createConfig = null
    h.state.requestInterceptor = null
    h.state.responseErrorInterceptor = null
    localStorage.clear()
    h.instance.get.mockResolvedValue({ data: {}, status: 200 })
    h.instance.post.mockResolvedValue({ data: {}, status: 200 })
    h.instance.put.mockResolvedValue({ data: {}, status: 200 })
  })

  // ===========================================================================
  // Defect proofs — behaviour the private instances did NOT have.
  // ===========================================================================

  describe('transport the private axios instances lacked', () => {
    it('attaches the autobot_access_token from localStorage when no SLM token exists', () => {
      // The private interceptors read `authStore.token` and nothing else, so an
      // operator holding only an autobot-issued token sent NO Authorization
      // header at all and every skills call 401'd.
      localStorage.setItem('autobot_access_token', 'autobot-token')
      useSkills()

      const headers = h.state.requestInterceptor!({ headers: {} }).headers

      expect(headers.Authorization).toBe('Bearer autobot-token')
    })

    it('clears the autobot_access_token on a 401', async () => {
      localStorage.setItem('autobot_access_token', 'stale-token')
      useSkills()

      await expect(
        h.state.responseErrorInterceptor!({ response: { status: 401 } })
      ).rejects.toBeDefined()

      expect(localStorage.getItem('autobot_access_token')).toBeNull()
    })

    it('drops the unexplained blanket 15s budget for the client default', () => {
      // 15000 was introduced with the feature (#731) and copied to the second
      // instance; nothing in history or comment justifies it, and it was too
      // SHORT for POST /skills/repos/{id}/sync, which awaits a git clone inline
      // (autobot-backend/api/skills_repos.py:117).
      useSkills()

      expect(h.state.createConfig?.timeout).toBe(30000)
      expect(h.state.createConfig?.timeout).not.toBe(15000)
    })

    it('resolves the base URL through the client rather than a private baseURL', () => {
      useSkills()

      expect(h.state.createConfig?.baseURL).toBe(BACKEND)
    })
  })

  // ===========================================================================
  // Regression guards — the wire contract must survive the migration.
  // These pass on both sides by design; they pin the paths, not a defect.
  // ===========================================================================

  describe('endpoint paths survive the migration (regression guard)', () => {
    it('fetchSkills GETs /skills/ with the trailing slash preserved', async () => {
      h.instance.get.mockResolvedValue({ data: { skills: [], categories: [] }, status: 200 })

      await useSkills().fetchSkills()

      expect(firstUrl('get')).toBe('/skills/')
    })

    it('fetchSkills serialises category + search as query params', async () => {
      h.instance.get.mockResolvedValue({ data: { skills: [], categories: [] }, status: 200 })

      await useSkills().fetchSkills('automation', 'web')

      expect(firstUrl('get')).toBe('/skills/?category=automation&search=web')
    })

    it('fetchCategories GETs /skills/categories', async () => {
      h.instance.get.mockResolvedValue({ data: { categories: { automation: 2 } }, status: 200 })

      const s = useSkills()
      await s.fetchCategories()

      expect(firstUrl('get')).toBe('/skills/categories')
      expect(s.categoryCounts.value).toEqual({ automation: 2 })
    })

    it('fetchSkillDetail GETs /skills/{name}', async () => {
      h.instance.get.mockResolvedValue({ data: { name: 'web_search' }, status: 200 })

      const s = useSkills()
      await s.fetchSkillDetail('web_search')

      expect(firstUrl('get')).toBe('/skills/web_search')
      expect(s.selectedSkill.value).toEqual({ name: 'web_search' })
    })

    it('enable/disable POST /skills/{name}/{verb}', async () => {
      h.instance.get.mockResolvedValue({ data: { skills: [], categories: [] }, status: 200 })

      await useSkills().enableSkill('web_search')
      await useSkills().disableSkill('web_search')

      expect(calls('post')[0][0]).toBe('/skills/web_search/enable')
      expect(calls('post')[1][0]).toBe('/skills/web_search/disable')
    })

    it('updateConfig PUTs the config under a `config` key', async () => {
      await useSkills().updateConfig('web_search', { depth: 3 })

      expect(calls('put')[0][0]).toBe('/skills/web_search/config')
      expect(calls('put')[0][1]).toEqual({ config: { depth: 3 } })
    })

    it('initializeSkills POSTs /skills/initialize', async () => {
      h.instance.get.mockResolvedValue({ data: { skills: [], categories: [] }, status: 200 })

      await useSkills().initializeSkills()

      expect(calls('post')[0][0]).toBe('/skills/initialize')
    })

    it('percent-encodes a skill name so a slash cannot escape the path', async () => {
      h.instance.get.mockResolvedValue({ data: { name: 'a/b' }, status: 200 })

      await useSkills().fetchSkillDetail('a/b')

      expect(firstUrl('get')).toBe('/skills/a%2Fb')
    })
  })

  describe('error surface', () => {
    it('surfaces the FastAPI detail rather than the axios message', async () => {
      h.instance.get.mockRejectedValue(detailError(500, 'skill registry unavailable'))

      const s = useSkills()
      await s.fetchSkills()

      expect(s.error.value).toBe('skill registry unavailable')
      expect(s.loading.value).toBe(false)
    })
  })
})

describe('useSkillGovernance — migrated onto useAutobotApi (#13079)', () => {
  beforeEach(() => {
    h.state.token = null
    h.state.createConfig = null
    localStorage.clear()
    h.instance.get.mockResolvedValue({ data: [], status: 200 })
    h.instance.post.mockResolvedValue({ data: {}, status: 200 })
    h.instance.put.mockResolvedValue({ data: {}, status: 200 })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // ===========================================================================
  // Defect proofs.
  // ===========================================================================

  it('surfaces the FastAPI detail instead of the axios status message', async () => {
    // The private instance's callers all read `e instanceof Error ? e.message`,
    // which under axios is the generic "Request failed with status code 403" —
    // the backend's reason for refusing a governance change never reached the
    // operator.
    h.instance.get.mockRejectedValue(detailError(403, 'governance is locked'))

    const g = useSkillGovernance()
    await g.fetchRepos()

    expect(g.error.value).toBe('governance is locked')
  })

  it('surfaces the detail on a refused approval decision', async () => {
    h.instance.post.mockRejectedValue(detailError(409, 'approval already decided'))

    const g = useSkillGovernance()
    await g.decideApproval('a1', true)

    expect(g.error.value).toBe('approval already decided')
  })

  it('gives the 30s approval poll a sub-interval timeout so ticks cannot overlap', () => {
    // The client default is 30s — the same length as the poll interval, so a
    // tick that ran to its budget would still be in flight as the next fired.
    vi.useFakeTimers()

    const g = useSkillGovernance()
    g.startApprovalPolling()
    vi.advanceTimersByTime(30_000)

    const [url, config] = calls('get')[0] as [string, { timeout: number }]
    expect(url).toBe('/skills/governance/approvals')
    expect(config?.timeout).toBe(SKILL_APPROVAL_POLL_TIMEOUT_MS)
    expect(config.timeout).toBeLessThan(30_000)

    g.stopApprovalPolling()
  })

  it('leaves an interactive approvals read on the client default budget', async () => {
    await useSkillGovernance().fetchApprovals()

    const [url, config] = calls('get')[0] as [string, unknown]
    expect(url).toBe('/skills/governance/approvals')
    expect(config).toBeUndefined()
  })

  // ===========================================================================
  // Regression guards.
  // ===========================================================================

  describe('endpoint paths survive the migration (regression guard)', () => {
    it('fetchRepos GETs /skills/repos', async () => {
      h.instance.get.mockResolvedValue({ data: [{ id: 'r1' }], status: 200 })

      const g = useSkillGovernance()
      await g.fetchRepos()

      expect(firstUrl('get')).toBe('/skills/repos')
      expect(g.repos.value).toEqual([{ id: 'r1' }])
    })

    it('addRepo POSTs the payload to /skills/repos then refreshes', async () => {
      await useSkillGovernance().addRepo({
        name: 'core',
        url: 'https://example.invalid/core.git',
        repo_type: 'git',
      })

      expect(calls('post')[0][0]).toBe('/skills/repos')
      expect(calls('post')[0][1]).toEqual({
        name: 'core',
        url: 'https://example.invalid/core.git',
        repo_type: 'git',
      })
      expect(firstUrl('get')).toBe('/skills/repos')
    })

    it('syncRepo POSTs /skills/repos/{id}/sync', async () => {
      await useSkillGovernance().syncRepo('r1')

      expect(calls('post')[0][0]).toBe('/skills/repos/r1/sync')
    })

    it('decideApproval POSTs the decision body to /skills/governance/approvals/{id}', async () => {
      await useSkillGovernance().decideApproval('a1', true, 'trusted', 'looks fine')

      expect(calls('post')[0][0]).toBe('/skills/governance/approvals/a1')
      expect(calls('post')[0][1]).toEqual({
        approved: true,
        notes: 'looks fine',
        trust_level: 'trusted',
      })
    })

    it('drafts GET /skills/governance/drafts and test/promote POST under it', async () => {
      h.instance.get.mockResolvedValue({ data: [{ id: 'd1' }], status: 200 })

      const g = useSkillGovernance()
      await g.fetchDrafts()
      await g.testDraft('d1')
      await g.promoteDraft('d1')

      expect(firstUrl('get')).toBe('/skills/governance/drafts')
      expect(calls('post')[0][0]).toBe('/skills/governance/drafts/d1/test')
      expect(calls('post')[1][0]).toBe('/skills/governance/drafts/d1/promote')
    })

    it('governance config GETs and PUTs /skills/governance/ with the trailing slash', async () => {
      h.instance.get.mockResolvedValue({ data: { mode: 'locked' }, status: 200 })

      const g = useSkillGovernance()
      await g.fetchGovernance()
      await g.setGovernanceMode('full_auto')

      expect(firstUrl('get')).toBe('/skills/governance/')
      expect(calls('put')[0][0]).toBe('/skills/governance/')
      expect(calls('put')[0][1]).toEqual({ mode: 'full_auto' })
    })
  })
})
