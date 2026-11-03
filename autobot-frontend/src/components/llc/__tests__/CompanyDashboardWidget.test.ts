// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// Company OS widgets (#18242): each type renders its section from the shared data.

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import CompanyDashboardWidget from '../CompanyDashboardWidget.vue'
import type { CompanyWidgetType } from '@/composables/dashboard/companyOsDashboard'
import type { CompanyDashboardData } from '@/views/llc/companyDashboardTypes'

const i18n = createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false, messages: { en: {} } })

const EMPTY: CompanyDashboardData = { agents: [], approvals: [], budgets: [], runs: [], activity: [] }

function render(type: CompanyWidgetType, data: Partial<CompanyDashboardData> = {}) {
  return mount(CompanyDashboardWidget, { props: { type, data: { ...EMPTY, ...data } }, global: { plugins: [i18n] } })
}

describe('CompanyDashboardWidget', () => {
  it('shows an empty state for approvals instead of disappearing from the grid', () => {
    expect(render('company-approvals').text()).toContain('llc.dashboard.noApprovals')
  })

  it('emits approve with the approval id', async () => {
    const approval = { id: 'a1', title: 'Hire', requested_by: 'ceo', created_at: '', issue_id: null }
    const wrapper = render('company-approvals', { approvals: [approval] })
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('approve')).toEqual([['a1']])
  })

  it('colours a budget bar from tokens by how much is spent', () => {
    const bar = render('company-budget', { budgets: [{ label: 'x', spent: 95, total: 100 }] }).find('.h-2.rounded-full.transition-all')
    expect(bar.classes()).toContain('bg-autobot-error')
    expect(bar.attributes('style')).toContain('width: 95%')
  })

  it('maps each run status to a kit badge variant', () => {
    const runs = (['done', 'running', 'failed'] as const).map((status, i) => ({ agent_id: 'a', agent_name: 'a', run_id: `r${i}`, status, started_at: '', duration_ms: 1500 }))
    const badges = render('company-runs', { runs }).findAll('.aui-badge')
    expect(badges.map((b) => b.classes().find((c) => /^aui-badge--(success|info|error)$/.test(c)))).toEqual([
      'aui-badge--success',
      'aui-badge--info',
      'aui-badge--error',
    ])
  })

  it('labels each run status with its i18n key, never the raw status value', () => {
    const runs = (['done', 'running', 'failed'] as const).map((status, i) => ({ agent_id: 'a', agent_name: 'a', run_id: `r${i}`, status, started_at: '', duration_ms: 1500 }))
    const labels = render('company-runs', { runs }).findAll('.aui-badge').map((b) => b.text())
    expect(labels).toEqual(['llc.dashboard.runStatus.done', 'llc.dashboard.runStatus.running', 'llc.dashboard.runStatus.failed'])
  })

  it('renders only the section its type names', () => {
    const text = render('company-activity').text()
    expect(text).toContain('llc.dashboard.liveActivity')
    expect(text).not.toContain('llc.dashboard.recentRuns')
  })

  it('tells same-named agents apart and marks the one the server says cannot run (#20519)', () => {
    const base = { title: '', status: 'idle' as const, adapter_type: 'autobot_agent', last_heartbeat: null }
    const agents = [
      { ...base, id: 'ceo-1', name: 'Alex', title: 'CEO', can_run: false, cannot_run_reason: 'no adapter_config.agent_class configured' },
      { ...base, id: 'dev-1', name: 'Alex', title: 'Engineer', can_run: true },
    ]
    const wrapper = render('company-agents', { agents })
    expect(wrapper.text()).toContain('Alex \u2014 CEO')
    expect(wrapper.text()).toContain('Alex \u2014 Engineer')
    const badges = wrapper.findAll('.aui-badge')
    expect(badges).toHaveLength(1)
    expect(badges[0].text()).toBe('llc.agent.cannotRun')
    expect(badges[0].attributes('title')).toBe('no adapter_config.agent_class configured')
  })
})
