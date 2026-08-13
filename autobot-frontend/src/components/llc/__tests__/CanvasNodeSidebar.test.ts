// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// GH#13940: the canvas node sidebar gets a fixed slot order — owner -> tools
// -> notes (overview/checklist/output) -> attributes — plus a right icon
// rail (info/checklist/cost/activity/handoff; comments is omitted, no
// endpoint exists). These tests assert rendered content and slot ORDER, and
// that a failed fetch renders "unavailable", never the same pixels as an
// empty result (#14064/#14104's precedent).

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const get = vi.fn()

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get, post: vi.fn() }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import CanvasNodeSidebar from '../CanvasNodeSidebar.vue'
import HandoffModal from '../HandoffModal.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

const AGENT_NODE = {
  id: 'dev',
  node_id: 'pk-dev-1',
  name: 'Grace',
  title: 'Engineer',
  status: 'idle' as const,
  adapter_type: 'claude_code',
  is_human: false,
  last_heartbeat: '2026-01-01T00:00:00Z',
  budget_spent: 3,
  budget_total: 10,
  assigned_item_count: 2,
  parent_id: null,
  children: [],
}

const HUMAN_NODE = {
  id: 'user:1',
  node_id: 'user-uuid-1',
  name: 'Alan',
  title: 'Advisor',
  status: 'idle' as const,
  adapter_type: 'human',
  is_human: true,
  last_heartbeat: null,
  budget_spent: 0,
  budget_total: 0,
  assigned_item_count: 0,
  parent_id: null,
  children: [],
}

function mountSidebar(node: typeof AGENT_NODE | typeof HUMAN_NODE) {
  return mount(CanvasNodeSidebar, {
    props: { node, companyId: 'c1', terminating: false },
    global: { plugins: [i18n], stubs: { HandoffModal: true } },
  })
}

beforeEach(() => {
  get.mockReset()
})

describe('fixed slot order (#13940 AC1: identical across node types)', () => {
  it('renders owner -> tools -> notes -> attributes, in that order, for an agent', () => {
    const wrapper = mountSidebar(AGENT_NODE)
    const ids = wrapper
      .findAll('[data-testid^="sidebar-slot-"]')
      .map((el) => el.attributes('data-testid'))
    expect(ids).toEqual([
      'sidebar-slot-owner',
      'sidebar-slot-tools',
      'sidebar-slot-notes',
      'sidebar-slot-attributes',
    ])
  })

  it('renders the identical order for a human node', () => {
    const wrapper = mountSidebar(HUMAN_NODE)
    const ids = wrapper
      .findAll('[data-testid^="sidebar-slot-"]')
      .map((el) => el.attributes('data-testid'))
    expect(ids).toEqual([
      'sidebar-slot-owner',
      'sidebar-slot-tools',
      'sidebar-slot-notes',
      'sidebar-slot-attributes',
    ])
  })

  it('shows the node identity in the owner slot', () => {
    const wrapper = mountSidebar(AGENT_NODE)
    expect(wrapper.get('[data-testid="sidebar-slot-owner"]').text()).toContain('Grace')
    expect(wrapper.get('[data-testid="sidebar-slot-owner"]').text()).toContain('Engineer')
  })

  it('shows the adapter as the tool for an agent, and "not applicable" for a person', () => {
    const agent = mountSidebar(AGENT_NODE)
    expect(agent.get('[data-testid="sidebar-slot-tools"]').text()).toContain('claude_code')

    const human = mountSidebar(HUMAN_NODE)
    expect(human.get('[data-testid="sidebar-slot-tools"]').text()).toContain(
      en.llc.orgChart.sidebar.toolsNotApplicable,
    )
  })
})

describe('icon rail (#13940)', () => {
  it('renders info -> checklist -> cost -> activity -> handoff, in that order', () => {
    const wrapper = mountSidebar(AGENT_NODE)
    const ids = wrapper
      .findAll('[data-testid^="sidebar-rail-"]')
      .map((el) => el.attributes('data-testid'))
    expect(ids).toEqual([
      'sidebar-rail-info',
      'sidebar-rail-checklist',
      'sidebar-rail-cost',
      'sidebar-rail-activity',
      'sidebar-rail-handoff',
    ])
  })

  it('never renders a "comments" rail icon — no endpoint exists for it', () => {
    const wrapper = mountSidebar(AGENT_NODE)
    expect(wrapper.find('[data-testid="sidebar-rail-comments"]').exists()).toBe(false)
  })
})

describe('checklist (Notes tab + rail): failed fetch is never rendered as empty (#14064/#14104)', () => {
  it('shows a loaded, non-terminal item', async () => {
    get.mockResolvedValueOnce([
      { id: 'wi-1', identifier: 'TASK-1', title: 'Ship it', status: 'in_progress', type: 'task' },
    ])
    const wrapper = mountSidebar(AGENT_NODE)
    await wrapper.get('[data-testid="sidebar-notes-tab-checklist"]').trigger('click')
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/api/llc/work-items?company_id=c1&assignee=pk-dev-1')
    expect(wrapper.get('[data-testid="sidebar-notes-content"]').text()).toContain('Ship it')
  })

  it('renders "unavailable" — not "no active items" — when the fetch rejects', async () => {
    get.mockRejectedValueOnce(new Error('network down'))
    const wrapper = mountSidebar(AGENT_NODE)
    await wrapper.get('[data-testid="sidebar-notes-tab-checklist"]').trigger('click')
    await flushPromises()

    const content = wrapper.get('[data-testid="sidebar-notes-content"]').text()
    expect(content).toContain(en.llc.orgChart.sidebar.itemsUnavailable)
    expect(content).not.toContain(en.llc.orgChart.sidebar.itemsEmpty)
  })

  it('renders "no active items" — not "unavailable" — on a genuinely empty result', async () => {
    get.mockResolvedValueOnce([])
    const wrapper = mountSidebar(AGENT_NODE)
    await wrapper.get('[data-testid="sidebar-notes-tab-checklist"]').trigger('click')
    await flushPromises()

    const content = wrapper.get('[data-testid="sidebar-notes-content"]').text()
    expect(content).toContain(en.llc.orgChart.sidebar.itemsEmpty)
    expect(content).not.toContain(en.llc.orgChart.sidebar.itemsUnavailable)
  })

  it('a human node never calls the API and renders the structural "not applicable" state', async () => {
    const wrapper = mountSidebar(HUMAN_NODE)
    await wrapper.get('[data-testid="sidebar-notes-tab-checklist"]').trigger('click')
    await flushPromises()

    expect(get).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="sidebar-notes-content"]').text()).toContain(
      en.llc.orgChart.sidebar.itemsNotApplicableHuman,
    )
  })

  it('puts finished items under Output, not Checklist, from the same fetch (no second request)', async () => {
    get.mockResolvedValueOnce([
      { id: 'wi-1', identifier: 'TASK-1', title: 'Open task', status: 'in_progress', type: 'task' },
      { id: 'wi-2', identifier: 'TASK-2', title: 'Finished task', status: 'done', type: 'task' },
    ])
    const wrapper = mountSidebar(AGENT_NODE)
    await wrapper.get('[data-testid="sidebar-notes-tab-checklist"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="sidebar-notes-content"]').text()).not.toContain('Finished task')

    await wrapper.get('[data-testid="sidebar-notes-tab-output"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="sidebar-notes-content"]').text()).toContain('Finished task')
    expect(get).toHaveBeenCalledTimes(1)
  })
})

describe('cost rail (#13940)', () => {
  it('renders the matched agent row', async () => {
    get.mockResolvedValueOnce([
      { agent_id: 'dev', agent_name: 'Grace', total_tokens: 900, cost_usd: '0.30' },
    ])
    const wrapper = mountSidebar(AGENT_NODE)
    await wrapper.get('[data-testid="sidebar-rail-cost"]').trigger('click')
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/api/llc/companies/c1/costs/by-agent-model')
    expect(wrapper.get('[data-testid="sidebar-panel-cost"]').text()).toContain('0.30')
  })

  it('renders "unavailable" on a failed fetch', async () => {
    get.mockRejectedValueOnce(new Error('down'))
    const wrapper = mountSidebar(AGENT_NODE)
    await wrapper.get('[data-testid="sidebar-rail-cost"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="sidebar-panel-cost"]').text()).toContain(
      en.llc.orgChart.sidebar.costUnavailable,
    )
  })

  it('never calls the API for a human node — structurally not applicable', async () => {
    const wrapper = mountSidebar(HUMAN_NODE)
    await wrapper.get('[data-testid="sidebar-rail-cost"]').trigger('click')
    await flushPromises()

    expect(get).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="sidebar-panel-cost"]').text()).toContain(
      en.llc.orgChart.sidebar.costNotApplicableHuman,
    )
  })
})

describe('activity rail (#13940)', () => {
  it('renders entries scoped to entity_type=agent and this node', async () => {
    get.mockResolvedValueOnce({
      items: [{ id: 'a1', action: 'agent_paused', occurred_at: new Date().toISOString() }],
      page: 1,
      page_size: 20,
      total: 1,
      has_next: false,
    })
    const wrapper = mountSidebar(AGENT_NODE)
    await wrapper.get('[data-testid="sidebar-rail-activity"]').trigger('click')
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/api/llc/companies/c1/activity?entity_type=agent&entity_id=dev&page_size=20')
    expect(wrapper.get('[data-testid="sidebar-panel-activity"]').text()).toContain('agent_paused')
  })
})

describe('handoff rail (#13940)', () => {
  it('opens HandoffModal with direction=to_human and the node PK', async () => {
    get.mockResolvedValueOnce([
      { id: 'wi-1', identifier: 'TASK-1', title: 'Ship it', status: 'in_progress', type: 'task' },
    ])
    const wrapper = mountSidebar(AGENT_NODE)
    await wrapper.get('[data-testid="sidebar-rail-handoff"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="sidebar-handoff-item-wi-1"]').trigger('click')

    const modal = wrapper.findComponent(HandoffModal)
    expect(modal.exists()).toBe(true)
    expect(modal.props('direction')).toBe('to_human')
    expect(modal.props('workItemId')).toBe('wi-1')
    expect(modal.props('agentAssigneeId')).toBe('pk-dev-1')
  })
})

describe('lifecycle controls stay wired (#13936/#13996 regression guard)', () => {
  it('emits pause/terminate with the node, unchanged from the pre-#13940 drawer', async () => {
    const wrapper = mountSidebar(AGENT_NODE)
    await wrapper.get('[data-testid="org-drawer-pause"]').trigger('click')
    expect(wrapper.emitted('pause')?.[0]).toEqual([AGENT_NODE])

    await wrapper.get('[data-testid="org-drawer-terminate"]').trigger('click')
    expect(wrapper.emitted('terminate')?.[0]).toEqual([AGENT_NODE])
  })

  it('a human node gets the "no agent controls" note instead of pause/terminate', () => {
    const wrapper = mountSidebar(HUMAN_NODE)
    expect(wrapper.find('[data-testid="org-drawer-pause"]').exists()).toBe(false)
    expect(wrapper.text()).toContain(en.llc.orgChart.humanNoAgentControls)
  })
})

// The activity rail mirrors the cost rail's three states. It was the only
// data-bearing slot with no coverage at all, which is how the honest-failure
// and not-applicable branches this umbrella exists to protect ended up
// asserted by nobody (#14064; same shape fixed on #14104 and #14169).
describe('activity rail: three distinct states (#13940)', () => {
  it('renders entries the API returned', async () => {
    get.mockResolvedValueOnce({
      items: [{ id: 'a1', action: 'Heartbeat completed', occurred_at: '2026-01-01T00:00:00Z' }],
    })
    const wrapper = mountSidebar(AGENT_NODE)
    await wrapper.get('[data-testid="sidebar-rail-activity"]').trigger('click')
    await flushPromises()

    expect(get).toHaveBeenCalledWith(
      expect.stringContaining('/api/llc/companies/c1/activity'),
    )
    expect(wrapper.get('[data-testid="sidebar-panel-activity"]').text()).toContain(
      'Heartbeat completed',
    )
  })

  it('renders "unavailable" — not "no activity" — when the fetch rejects', async () => {
    get.mockRejectedValueOnce(new Error('down'))
    const wrapper = mountSidebar(AGENT_NODE)
    await wrapper.get('[data-testid="sidebar-rail-activity"]').trigger('click')
    await flushPromises()

    const panel = wrapper.get('[data-testid="sidebar-panel-activity"]').text()
    expect(panel).toContain(en.llc.orgChart.sidebar.activityUnavailable)
    // A failed fetch must never be reported as an absence of activity.
    expect(panel).not.toContain(en.llc.orgChart.sidebar.activityEmpty)
  })

  it('renders "no activity" — not "unavailable" — on a genuinely empty result', async () => {
    get.mockResolvedValueOnce({ items: [] })
    const wrapper = mountSidebar(AGENT_NODE)
    await wrapper.get('[data-testid="sidebar-rail-activity"]').trigger('click')
    await flushPromises()

    const panel = wrapper.get('[data-testid="sidebar-panel-activity"]').text()
    expect(panel).toContain(en.llc.orgChart.sidebar.activityEmpty)
    expect(panel).not.toContain(en.llc.orgChart.sidebar.activityUnavailable)
  })

  it('a human node never calls the API and says so structurally', async () => {
    const wrapper = mountSidebar(HUMAN_NODE)
    await wrapper.get('[data-testid="sidebar-rail-activity"]').trigger('click')
    await flushPromises()

    expect(get).not.toHaveBeenCalled()
    const panel = wrapper.get('[data-testid="sidebar-panel-activity"]').text()
    expect(panel).toContain(en.llc.orgChart.sidebar.activityNotApplicableHuman)
    // "Not applicable" and "none" are different claims about a person.
    expect(panel).not.toContain(en.llc.orgChart.sidebar.activityEmpty)
  })

  it('does not refetch when the rail is re-entered', async () => {
    get.mockResolvedValueOnce({ items: [] })
    const wrapper = mountSidebar(AGENT_NODE)
    await wrapper.get('[data-testid="sidebar-rail-activity"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="sidebar-rail-info"]').trigger('click')
    await wrapper.get('[data-testid="sidebar-rail-activity"]').trigger('click')
    await flushPromises()

    expect(get).toHaveBeenCalledTimes(1)
  })
})

describe('rail switching drives the notes tab and the handoff slot (#13940)', () => {
  it('the info icon returns the notes pane to Overview', async () => {
    get.mockResolvedValue({ items: [] })
    const wrapper = mountSidebar(AGENT_NODE)
    await wrapper.get('[data-testid="sidebar-rail-checklist"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="sidebar-rail-info"]').trigger('click')

    expect(wrapper.get('[data-testid="sidebar-notes-tab-overview"]').classes().join(' ')).toMatch(
      /autobot-/,
    )
  })

  it('the handoff rail loads the assignable items for an agent', async () => {
    get.mockResolvedValue([{ id: 'w1', title: 'Ship it', status: 'in_progress' }])
    const wrapper = mountSidebar(AGENT_NODE)
    await wrapper.get('[data-testid="sidebar-rail-handoff"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="sidebar-panel-handoff"]').exists()).toBe(true)
    expect(get).toHaveBeenCalled()
  })

  it('the handoff rail is structurally not applicable for a person', async () => {
    const wrapper = mountSidebar(HUMAN_NODE)
    await wrapper.get('[data-testid="sidebar-rail-handoff"]').trigger('click')
    await flushPromises()

    expect(get).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="sidebar-panel-handoff"]').text()).toContain(
      en.llc.orgChart.sidebar.handoffNotApplicableHuman,
    )
  })
})

describe('state that must not go stale (#13940)', () => {
  it('refetches the assigned items after a handoff completes', async () => {
    // The item just moved off this agent. Trusting the stale list would show a
    // work item under an owner who no longer has it — a wrong statement about
    // ownership, which is the class this umbrella keeps finding.
    get.mockResolvedValue([{ id: 'w1', title: 'Ship it', status: 'in_progress' }])
    const wrapper = mountSidebar(AGENT_NODE)
    await wrapper.get('[data-testid="sidebar-rail-handoff"]').trigger('click')
    await flushPromises()
    const callsBefore = get.mock.calls.length

    await wrapper.get('[data-testid="sidebar-handoff-item-w1"]').trigger('click')
    wrapper.findComponent(HandoffModal).vm.$emit('done')
    await flushPromises()

    expect(get.mock.calls.length).toBeGreaterThan(callsBefore)
  })

  it('does not refetch the cost rail when it is re-entered', async () => {
    get.mockResolvedValue([])
    const wrapper = mountSidebar(AGENT_NODE)
    await wrapper.get('[data-testid="sidebar-rail-cost"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="sidebar-rail-info"]').trigger('click')
    await wrapper.get('[data-testid="sidebar-rail-cost"]').trigger('click')
    await flushPromises()

    expect(get).toHaveBeenCalledTimes(1)
  })

  it('renders "never" for a freshly hired agent that has not run yet', () => {
    // Only agents render a heartbeat (a person's row says "not applicable"),
    // so the null branch belongs to a just-hired agent — a real state, not a
    // defensive one. An empty cell there would read as "ran, but we lost when".
    const wrapper = mountSidebar({ ...AGENT_NODE, last_heartbeat: null })

    expect(wrapper.get('[data-testid="node-sidebar"]').text()).toContain(en.llc.orgChart.never)
  })
})

// #13945 added a labelled Role row for people. Moving the drawer into this
// component dropped it, and nothing failed — no test had ever asserted it. The
// guard exists so the next refactor cannot repeat that silently.
describe('a person keeps their Role attribute (#13945 regression guard)', () => {
  it('renders a labelled Role row for a human node', () => {
    const wrapper = mountSidebar(HUMAN_NODE)

    const row = wrapper.get('[data-testid="sidebar-attr-role"]')
    expect(row.text()).toContain(en.llc.orgChart.role)
    expect(row.text()).toContain(HUMAN_NODE.title)
  })

  it('does not render a Role row for an agent — its role is the adapter row', () => {
    const wrapper = mountSidebar(AGENT_NODE)

    expect(wrapper.find('[data-testid="sidebar-attr-role"]').exists()).toBe(false)
  })

  it('leaves a person with at least one attribute that is actually about them', () => {
    // The other three attribute rows all read "not applicable" for a human, so
    // dropping Role empties the slot entirely — the failure this guards.
    const text = mountSidebar(HUMAN_NODE).get('[data-testid="sidebar-slot-attributes"]').text()
    const notApplicable = en.llc.orgChart.sidebar.toolsNotApplicable

    expect(text.split(notApplicable).length - 1).toBeLessThan(4)
    expect(text).toContain(HUMAN_NODE.title)
  })
})
