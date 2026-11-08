// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #17514 — the Agent Activity Monitor shows what was measured and says what was not.
 * Every card used to read "0 Tasks / 0s Uptime" under "0 active" for agents nobody measured,
 * and five agents named "CEO" were five identical cards.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/utils/ApiClient', () => ({ default: { get } }))

import AgentActivityVisualization from '../AgentActivityVisualization.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en }, missingWarn: false, fallbackWarn: false })
const A = en.visualizations.agentActivity

function unmeasured(id: string, companyName: string | null) {
  return {
    id, name: 'CEO', type: 'orchestrator', status: null, companyId: companyName ? `${id}-co` : null, companyName,
    currentTask: null, tasksCompleted: null, uptime: null, successRate: null, recentTasks: [], activityTimeline: [],
  }
}

async function render(agents: unknown[]) {
  get.mockImplementation(async (url?: string) => (String(url).includes('/agents/status') ? { agents } : { tasks: [] }))
  const w = mount(AgentActivityVisualization, {
    props: { autoRefresh: false },
    global: { plugins: [i18n], stubs: { Icon: true } },
  })
  await flushPromises()
  return w
}

beforeEach(() => get.mockReset())

describe('Agent Activity Monitor reports only what it measured (#17514)', () => {
  it('an agent with no activity data reads "not reported", never a measured zero', async () => {
    const w = await render([unmeasured('ceo-1', 'Acme')])
    const metrics = w.get('.agent-metrics').text()
    expect(metrics).toContain(A.notReported)
    expect(metrics).not.toMatch(/(^|\s)0(\s|s|$)/)
    expect(w.text()).toContain(A.statusNotReported)
  })

  it('the header says statuses were not reported instead of "0 active"', async () => {
    const w = await render([unmeasured('ceo-1', 'Acme'), unmeasured('ceo-2', 'Globex')])
    const header = w.get('.active-count').text()
    expect(header).toContain(A.statusNotReported)
    expect(header).not.toContain(A.activeCount.replace('{count}', '0'))
  })

  it('two agents called CEO name their companies, so the cards differ', async () => {
    const w = await render([unmeasured('ceo-1', 'Acme'), unmeasured('ceo-2', 'Globex')])
    const cards = w.findAll('.agent-info').map((c) => c.text())
    expect(cards).toHaveLength(2)
    expect(cards[0]).toContain('Acme')
    expect(cards[1]).toContain('Globex')
  })

  it('a reported status still counts toward "active"', async () => {
    const working = { ...unmeasured('w', null), status: 'working', tasksCompleted: 3, uptime: 120, successRate: 100 }
    const w = await render([working])
    expect(w.get('.active-count').text()).toContain(A.activeCount.replace('{count}', '1'))
    expect(w.get('.agent-metrics').text()).toContain('3')
  })
})
