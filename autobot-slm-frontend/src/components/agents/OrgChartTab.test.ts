// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #13079 — OrgChartTab reaches the autobot backend through `useAutobotApi`.
 *
 * The tab used to own a private `fetch` with an `Authorization:
 * Bearer ${authStore.token}` header computed inline, so it lost the
 * `autobot_access_token` fallback, the 401 cleanup and the 30s timeout that
 * `useAutobotApi` applies (asserted in useAutobotApi.test.ts).
 *
 * Stubbing `axios.create` keeps these assertions on the wire contract: the
 * exact endpoint paths and verbs, and the per-panel degradation the old
 * `fetch`-with-`res.ok` checks provided — `fetch` never rejects on a non-2xx,
 * so one failing detail panel must still leave the other two populated.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import axios from 'axios'
import OrgChartTab from './OrgChartTab.vue'
import en from '@/locales/en.json'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 'test-token' }),
}))

vi.mock('axios', () => {
  const instance = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: { use: () => undefined },
      response: { use: () => undefined },
    },
  }
  return { default: { create: () => instance } }
})

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

type MockedClient = { get: ReturnType<typeof vi.fn>; post: ReturnType<typeof vi.fn> }

function client(): MockedClient {
  return (axios.create as unknown as () => MockedClient)()
}

const NODE = {
  agent_id: 'orchestrator',
  name: 'Orchestrator',
  org_role: 'manager',
  title: 'Lead',
  capabilities: 'planning',
  direct_reports_count: 1,
  children: [],
}

function payloadFor(url: string): unknown {
  if (url.endsWith('/agents/org')) return [NODE]
  if (url.endsWith('/reports')) return [{ agent_id: 'worker', name: 'Worker', org_role: 'worker' }]
  if (url.endsWith('/activity')) {
    return { manager_id: 'orchestrator', total_delegated: 3, by_status: { completed: 3 } }
  }
  if (url.includes('/delegations')) {
    return [
      {
        id: 'd1',
        delegator_id: 'orchestrator',
        assignee_id: 'worker',
        task_description: 'ship it',
        status: 'completed',
        escalated_to: null,
        created_at: '2026-01-01T00:00:00Z',
      },
    ]
  }
  return { success: true }
}

function urlsOf(fn: ReturnType<typeof vi.fn>): string[] {
  return fn.mock.calls.map((c) => c[0] as string)
}

describe('OrgChartTab transport (#13079)', () => {
  beforeEach(() => {
    const c = client()
    c.get.mockReset()
    c.post.mockReset()
    c.get.mockImplementation(async (url: string) => ({ data: payloadFor(url), status: 200 }))
    c.post.mockImplementation(async (url: string) => ({ data: payloadFor(url), status: 200 }))
  })

  it('loads the org tree from /agents/org on mount', async () => {
    const wrapper = mount(OrgChartTab, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(urlsOf(client().get)).toContain('/agents/org')
    expect(wrapper.text()).toContain('Orchestrator')
  })

  it('fans out to reports, activity and delegations when a node is selected', async () => {
    const wrapper = mount(OrgChartTab, { global: { plugins: [i18n] } })
    await flushPromises()

    await (wrapper.vm as unknown as { selectNode: (n: unknown) => Promise<void> }).selectNode(NODE)
    await flushPromises()

    const urls = urlsOf(client().get)
    expect(urls).toContain('/agents/orchestrator/reports')
    expect(urls).toContain('/agents/orchestrator/activity')
    expect(urls).toContain('/agents/orchestrator/delegations?role=delegator&limit=10')
  })

  it('keeps the surviving detail panels when one of the three calls fails', async () => {
    const wrapper = mount(OrgChartTab, { global: { plugins: [i18n] } })
    await flushPromises()

    client().get.mockImplementation(async (url: string) => {
      if (url.endsWith('/reports')) throw new Error('boom')
      return { data: payloadFor(url), status: 200 }
    })

    const vm = wrapper.vm as unknown as {
      selectNode: (n: unknown) => Promise<void>
      directReports: unknown[]
      activity: unknown
      delegations: unknown[]
    }
    await vm.selectNode(NODE)
    await flushPromises()

    expect(vm.directReports).toEqual([])
    expect(vm.activity).not.toBeNull()
    expect(vm.delegations).toHaveLength(1)
  })

  it('POSTs a delegation and surfaces the backend detail on failure', async () => {
    const wrapper = mount(OrgChartTab, { global: { plugins: [i18n] } })
    await flushPromises()

    const vm = wrapper.vm as unknown as {
      selectNode: (n: unknown) => Promise<void>
      submitDelegation: () => Promise<void>
      delegateForm: { assignee_id: string; task_description: string }
      delegateError: string | null
    }
    await vm.selectNode(NODE)
    vm.delegateForm.assignee_id = 'worker'
    vm.delegateForm.task_description = 'ship it'

    await vm.submitDelegation()
    await flushPromises()

    const [url, body] = client().post.mock.calls[0] as [string, unknown]
    expect(url).toBe('/agents/orchestrator/delegate')
    expect(body).toEqual({ assignee_id: 'worker', task_description: 'ship it' })

    client().post.mockRejectedValue({ response: { data: { detail: 'not a manager' } } })
    await vm.submitDelegation()
    await flushPromises()

    expect(vm.delegateError).toBe('not a manager')
  })

  it('shows the backend detail when the tree load fails', async () => {
    client().get.mockRejectedValue({ response: { data: { detail: 'org registry offline' } } })

    const wrapper = mount(OrgChartTab, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(wrapper.text()).toContain('org registry offline')
  })
})
