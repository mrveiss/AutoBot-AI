// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #13079 — useSkills / useSkillGovernance migrated off their two private
 * `axios.create` instances onto `useAutobotApi`.
 *
 * Both used to attach only `Bearer ${authStore.token}` — no `autobot_access_token`
 * fallback, no 401 cleanup — which is exactly the fork that made `AdvancedControlTool`
 * 401 while its ~17 siblings worked (#13077). They now share the SLM's `SlmApiClient`
 * pointed at the main backend (#12363); its token, 401 and timeout handling are tested
 * once in `utils/ApiClient.test.ts`. The client is the shared `mockAutobotBackendClient`
 * double: methods resolve the parsed body and failures are the kit `HttpError`. These
 * tests pin the base URL, the wire paths, and the error surface.
 *
 * Which tests prove a defect and which are regression guards is stated per
 * `describe` block below.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { HttpError } from '@autobot/ui'
import { backendClient } from '@/testing/mockAutobotBackendClient'

const BACKEND = 'http://autobot.example/autobot-api'

vi.mock('@/utils/ApiClient', async (importOriginal) =>
  (await import('@/testing/mockAutobotBackendClient')).withMockedBackendClient(importOriginal),
)
vi.mock('@/config/ssot-config', () => ({ getBackendUrl: () => BACKEND }))

import { useSkills, useSkillGovernance } from './useSkills'
import { SKILL_APPROVAL_POLL_TIMEOUT_MS } from '@/constants/api-timeouts'

/** The single client every call in this module shares. */
function calls(verb: 'get' | 'post' | 'put') {
  return backendClient[verb].mock.calls as unknown[][]
}

function firstUrl(verb: 'get' | 'post' | 'put'): string {
  return calls(verb)[0]?.[0] as string
}

/** A kit `HttpError` carrying a FastAPI `{ detail }` body. */
function detailError(status: number, detail: string) {
  return new HttpError(status, 'Error', { detail })
}

describe('useSkills — migrated onto useAutobotApi (#13079)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    backendClient.baseUrl = null
    backendClient.get.mockResolvedValue({})
    backendClient.post.mockResolvedValue({})
    backendClient.put.mockResolvedValue({})
  })

  // ===========================================================================
  // Defect proofs — behaviour the private instances did NOT have.
  // ===========================================================================

  describe('transport the private axios instances lacked', () => {
    it('resolves the base URL through the client rather than a private baseURL', () => {
      useSkills()

      expect(backendClient.baseUrl).toBe(BACKEND)
    })
  })

  // ===========================================================================
  // Regression guards — the wire contract must survive the migration.
  // These pass on both sides by design; they pin the paths, not a defect.
  // ===========================================================================

  describe('endpoint paths survive the migration (regression guard)', () => {
    it('fetchSkills GETs /skills/ with the trailing slash preserved', async () => {
      backendClient.get.mockResolvedValue({ skills: [], categories: [] })

      await useSkills().fetchSkills()

      expect(firstUrl('get')).toBe('/skills/')
    })

    it('fetchSkills serialises category + search as query params', async () => {
      backendClient.get.mockResolvedValue({ skills: [], categories: [] })

      await useSkills().fetchSkills('automation', 'web')

      expect(firstUrl('get')).toBe('/skills/?category=automation&search=web')
    })

    it('fetchCategories GETs /skills/categories', async () => {
      backendClient.get.mockResolvedValue({ categories: { automation: 2 } })

      const s = useSkills()
      await s.fetchCategories()

      expect(firstUrl('get')).toBe('/skills/categories')
      expect(s.categoryCounts.value).toEqual({ automation: 2 })
    })

    it('fetchSkillDetail GETs /skills/{name}', async () => {
      backendClient.get.mockResolvedValue({ name: 'web_search' })

      const s = useSkills()
      await s.fetchSkillDetail('web_search')

      expect(firstUrl('get')).toBe('/skills/web_search')
      expect(s.selectedSkill.value).toEqual({ name: 'web_search' })
    })

    it('enable/disable POST /skills/{name}/{verb}', async () => {
      backendClient.get.mockResolvedValue({ skills: [], categories: [] })

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
      backendClient.get.mockResolvedValue({ skills: [], categories: [] })

      await useSkills().initializeSkills()

      expect(calls('post')[0][0]).toBe('/skills/initialize')
    })

    it('percent-encodes a skill name so a slash cannot escape the path', async () => {
      backendClient.get.mockResolvedValue({ name: 'a/b' })

      await useSkills().fetchSkillDetail('a/b')

      expect(firstUrl('get')).toBe('/skills/a%2Fb')
    })
  })

  describe('error surface', () => {
    it('surfaces the FastAPI detail rather than the generic HttpError message', async () => {
      backendClient.get.mockRejectedValue(detailError(500, 'skill registry unavailable'))

      const s = useSkills()
      await s.fetchSkills()

      expect(s.error.value).toBe('skill registry unavailable')
      expect(s.loading.value).toBe(false)
    })

    it('renders a plain Error as the translated generic message plus the cause, once', async () => {
      backendClient.get.mockRejectedValue(new Error('boom'))

      const s = useSkills()
      await s.fetchSkills()

      expect(s.error.value).toBe('Skills request failed: boom')
    })

    it('renders a detail-less HttpError as the translated generic message and the status', async () => {
      backendClient.get.mockRejectedValue(new HttpError(500, 'Internal Server Error'))

      const s = useSkills()
      await s.fetchSkills()

      expect(s.error.value).toBe('Skills request failed (HTTP 500)')
    })
  })
})

describe('useSkillGovernance — migrated onto useAutobotApi (#13079)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    backendClient.baseUrl = null
    backendClient.get.mockResolvedValue([])
    backendClient.post.mockResolvedValue({})
    backendClient.put.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // ===========================================================================
  // Defect proofs.
  // ===========================================================================

  it('surfaces the FastAPI detail instead of the generic status message', async () => {
    // The private instance's callers all read `e instanceof Error ? e.message`,
    // which is the generic status message —
    // the backend's reason for refusing a governance change never reached the
    // operator.
    backendClient.get.mockRejectedValue(detailError(403, 'governance is locked'))

    const g = useSkillGovernance()
    await g.fetchRepos()

    expect(g.error.value).toBe('governance is locked')
  })

  it('surfaces the detail on a refused approval decision', async () => {
    backendClient.post.mockRejectedValue(detailError(409, 'approval already decided'))

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

    const [url, config] = calls('get')[0] as [string, { timeout: number; maxRetries: number }]
    expect(url).toBe('/skills/governance/approvals')
    expect(config?.timeout).toBe(SKILL_APPROVAL_POLL_TIMEOUT_MS)
    expect(config.timeout).toBeLessThan(30_000)
    // GET retries would stretch one failing tick past the interval (#12363)
    expect(config.maxRetries).toBe(1)

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
      backendClient.get.mockResolvedValue([{ id: 'r1' }])

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
      backendClient.get.mockResolvedValue([{ id: 'd1' }])

      const g = useSkillGovernance()
      await g.fetchDrafts()
      await g.testDraft('d1')
      await g.promoteDraft('d1')

      expect(firstUrl('get')).toBe('/skills/governance/drafts')
      expect(calls('post')[0][0]).toBe('/skills/governance/drafts/d1/test')
      expect(calls('post')[1][0]).toBe('/skills/governance/drafts/d1/promote')
    })

    it('governance config GETs and PUTs /skills/governance/ with the trailing slash', async () => {
      backendClient.get.mockResolvedValue({ mode: 'locked' })

      const g = useSkillGovernance()
      await g.fetchGovernance()
      await g.setGovernanceMode('full_auto')

      expect(firstUrl('get')).toBe('/skills/governance/')
      expect(calls('put')[0][0]).toBe('/skills/governance/')
      expect(calls('put')[0][1]).toEqual({ mode: 'full_auto' })
    })
  })
})
