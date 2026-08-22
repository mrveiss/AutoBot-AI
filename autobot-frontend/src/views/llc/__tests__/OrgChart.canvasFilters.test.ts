// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #14608: the Company OS canvas filters by exactly one property. These tests
// pin the multi-filter that composes with the existing "View As: role" lens
// (#13943) rather than replacing it — role, team and tool combine with AND,
// the active set is always visible without opening a menu, and an emptied
// canvas still reads as filtered, never as "no data" (#14064, #13617,
// #14556's repeat failure shape).
//
// `OrgChart.roleLens.test.ts` is re-run unmodified (in the same run this
// suite is reported alongside) to pin the hard requirement that the
// single-role lens keeps working exactly as it did before this issue.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { ref } from 'vue'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
const post = vi.fn()
const push = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get, post }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
  useRoute: () => ({ params: { companyId: 'c1' }, query: {} }),
}))

const companyRef = ref('c1')
vi.mock('@/composables/llc/useLlcCompanyContext', () => ({
  useLlcCompanyContext: () => ({
    companyId: companyRef,
    resolveCompanyId: () => Promise.resolve(companyRef.value),
  }),
}))

import OrgChart from '../OrgChart.vue'
import WorkflowCanvas from '@/components/workflow/WorkflowCanvas.vue'
import { ORG_GROUP_PREFIX, TEAM_GROUP_PREFIX } from '@/composables/llc/orgCanvasGraph'

const USER_ID_1 = '11111111-1111-1111-1111-111111111111'
const USER_ID_2 = '22222222-2222-2222-2222-222222222222'
const USER_ID_3 = '33333333-3333-3333-3333-333333333333'

/** ceo unit: ceo (Manager) -> dev (agent, Engineer). Three ungrouped humans:
 * Grace and Ivan are both Engineers on different teams; Hana is a Designer. */
const PEOPLE = [
  {
    id: 'ceo',
    name: 'Ada',
    title: 'Manager',
    status: 'idle',
    adapter_type: 'claude',
    is_human: false,
    last_heartbeat: null,
    budget_spent: 0,
    budget_total: 0,
    assigned_item_count: 0,
    parent_id: null,
    children: [
      {
        id: 'dev',
        name: 'Deputy',
        title: 'Engineer',
        status: 'idle',
        adapter_type: 'claude',
        is_human: false,
        last_heartbeat: null,
        budget_spent: 0,
        budget_total: 0,
        assigned_item_count: 0,
        parent_id: 'ceo',
        children: [],
      },
    ],
  },
  {
    id: `user:${USER_ID_1}`,
    node_id: USER_ID_1,
    name: 'Grace',
    title: 'Engineer',
    status: 'idle',
    adapter_type: 'human',
    is_human: true,
    last_heartbeat: null,
    budget_spent: 0,
    budget_total: 0,
    assigned_item_count: 0,
    parent_id: null,
    children: [],
  },
  {
    id: `user:${USER_ID_2}`,
    node_id: USER_ID_2,
    name: 'Hana',
    title: 'Designer',
    status: 'idle',
    adapter_type: 'human',
    is_human: true,
    last_heartbeat: null,
    budget_spent: 0,
    budget_total: 0,
    assigned_item_count: 0,
    parent_id: null,
    children: [],
  },
  {
    id: `user:${USER_ID_3}`,
    node_id: USER_ID_3,
    name: 'Ivan',
    title: 'Engineer',
    status: 'idle',
    adapter_type: 'human',
    is_human: true,
    last_heartbeat: null,
    budget_spent: 0,
    budget_total: 0,
    assigned_item_count: 0,
    parent_id: null,
    children: [],
  },
]

const TEAMS = [
  { id: 't-platform', name: 'Platform', member_user_ids: [USER_ID_1] },
  { id: 't-design', name: 'Design', member_user_ids: [USER_ID_2, USER_ID_3] },
]

const TOOLS = [
  { role_id: 'r-eng', role_name: 'Engineer', tool_name: 'web_search' },
  { role_id: 'r-mgr', role_name: 'Manager', tool_name: 'jira' },
]

const PROCESSES = [
  { role_id: 'r-eng', role_name: 'Engineer', workflow_id: 'wf-eng' },
  { role_id: 'r-mgr', role_name: 'Manager', workflow_id: 'wf-mgr' },
]

interface Fixture {
  people?: unknown[]
  teams?: unknown[]
  tools?: unknown[]
  processes?: unknown[]
}

function mockApi({ people = PEOPLE, teams = TEAMS, tools = TOOLS, processes = PROCESSES }: Fixture = {}): void {
  get.mockImplementation((url: string) => {
    if (url === '/api/llc/companies/c1/org-chart') return Promise.resolve({ nodes: structuredClone(people) })
    if (url === '/api/llc/companies/c1/work-items/executor-rollup') return Promise.resolve({ cells: [] })
    if (url === '/api/llc/companies/c1/process-nodes') return Promise.resolve({ nodes: structuredClone(processes) })
    if (url === '/api/llc/companies/c1/tool-nodes') return Promise.resolve({ nodes: structuredClone(tools) })
    if (url === '/api/llc/roles/c1') return Promise.resolve([])
    if (url === '/api/llc/contacts/c1/involved') return Promise.resolve({ with_role: [], unassigned: [] })
    if (url === '/api/llc/companies/c1/teams') return Promise.resolve({ teams: structuredClone(teams) })
    throw new Error(`unexpected GET ${url}`)
  })
}

async function mountOnCanvas(fixture?: Fixture) {
  mockApi(fixture)
  const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
  const wrapper = mount(OrgChart, { global: { plugins: [i18n], stubs: { HireAgentModal: true } } })
  await flushPromises()
  await wrapper.get('[data-testid="org-view-canvas"]').trigger('click')
  await flushPromises()
  return wrapper
}

function canvasNodeIds(wrapper: Awaited<ReturnType<typeof mountOnCanvas>>): string[] {
  return wrapper.findComponent(WorkflowCanvas).props('nodes').map((n: { id: string }) => n.id)
}

beforeEach(() => {
  get.mockReset()
  post.mockReset()
  push.mockReset()
  post.mockResolvedValue({})
})

describe('OrgChart multi-filter (#14608): pickers and visibility', () => {
  it('offers a team filter option per team, plus "all teams"', async () => {
    const wrapper = await mountOnCanvas()
    const options = wrapper.findAll('[data-testid="team-filter-select"] option').map((o) => o.text())
    expect(options).toEqual([
      en.llc.orgChart.teamFilterAll,
      'Platform',
      'Design',
      en.llc.orgChart.peopleNoTeam,
    ])
  })

  it('offers a tool filter option per tool, plus "all tools"', async () => {
    const wrapper = await mountOnCanvas()
    const options = wrapper.findAll('[data-testid="tool-filter-select"] option').map((o) => o.text())
    expect(options).toEqual([en.llc.orgChart.toolFilterAll, 'jira', 'web_search'])
  })

  it('offers no team/tool controls when the company has neither', async () => {
    const wrapper = await mountOnCanvas({ teams: [], tools: [] })
    expect(wrapper.find('[data-testid="team-filter-control"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="tool-filter-control"]').exists()).toBe(false)
  })

  it('shows every active filter banner at once — the set is visible without opening a menu', async () => {
    const wrapper = await mountOnCanvas()

    await wrapper.get('[data-testid="role-lens-select"]').setValue('Engineer')
    await wrapper.get('[data-testid="team-filter-select"]').setValue('t-design')
    await wrapper.get('[data-testid="tool-filter-select"]').setValue('web_search')
    await flushPromises()

    expect(wrapper.get('[data-testid="role-lens-banner"]').text()).toContain('Engineer')
    expect(wrapper.get('[data-testid="team-filter-banner"]').text()).toContain('Design')
    expect(wrapper.get('[data-testid="tool-filter-banner"]').text()).toContain('web_search')
  })
})

describe('OrgChart multi-filter (#14608): team and tool combine with AND', () => {
  it('role + team narrow to the intersection — removing either widens the result', async () => {
    const wrapper = await mountOnCanvas()

    await wrapper.get('[data-testid="role-lens-select"]').setValue('Engineer')
    await wrapper.get('[data-testid="team-filter-select"]').setValue('t-design')
    await flushPromises()
    const combinedIds = canvasNodeIds(wrapper)
    // Only Ivan is both an Engineer and on Design.
    expect(combinedIds).toContain(`user:${USER_ID_3}`)
    expect(combinedIds).not.toContain(`user:${USER_ID_1}`) // Engineer, but Platform
    expect(combinedIds).not.toContain(`user:${USER_ID_2}`) // Design, but Designer
    expect(combinedIds).not.toContain('dev') // Engineer, but no team

    // Removing team widens it — Grace and dev (also Engineers) come back.
    await wrapper.get('[data-testid="team-filter-select"]').setValue('')
    await flushPromises()
    const roleOnlyIds = canvasNodeIds(wrapper)
    expect(roleOnlyIds).toContain(`user:${USER_ID_1}`)
    expect(roleOnlyIds).toContain('dev')
    expect(roleOnlyIds.length).toBeGreaterThan(combinedIds.length)
  })

  it('team + tool narrow to the intersection — removing either widens the result', async () => {
    const wrapper = await mountOnCanvas()

    await wrapper.get('[data-testid="team-filter-select"]').setValue('t-design')
    await wrapper.get('[data-testid="tool-filter-select"]').setValue('web_search')
    await flushPromises()
    const combinedIds = canvasNodeIds(wrapper)
    // web_search is carried by "Engineer" — only Ivan (Design + Engineer).
    expect(combinedIds).toContain(`user:${USER_ID_3}`)
    expect(combinedIds).not.toContain(`user:${USER_ID_2}`) // Design, but Designer

    // Removing tool widens it — Hana (Design, any role) comes back.
    await wrapper.get('[data-testid="tool-filter-select"]').setValue('')
    await flushPromises()
    const teamOnlyIds = canvasNodeIds(wrapper)
    expect(teamOnlyIds).toContain(`user:${USER_ID_2}`)
    expect(teamOnlyIds.length).toBeGreaterThan(combinedIds.length)
  })

  it('a tool filter also narrows the process grid to the steps that tool touches', async () => {
    const wrapper = await mountOnCanvas()

    await wrapper.get('[data-testid="tool-filter-select"]').setValue('web_search')
    await flushPromises()

    const ids = canvasNodeIds(wrapper)
    expect(ids).toContain('process:r-eng:wf-eng')
    expect(ids).not.toContain('process:r-mgr:wf-mgr')
  })

  it('a tool filter narrows the tool grid to the one selected tool', async () => {
    const wrapper = await mountOnCanvas()

    await wrapper.get('[data-testid="tool-filter-select"]').setValue('web_search')
    await flushPromises()

    const ids = canvasNodeIds(wrapper)
    expect(ids).toContain('tool:web_search')
    expect(ids).not.toContain('tool:jira')
  })

  it('never fetches or posts as a result of a team/tool selection — presentation only', async () => {
    const wrapper = await mountOnCanvas()
    get.mockClear()
    post.mockClear()

    await wrapper.get('[data-testid="team-filter-select"]').setValue('t-design')
    await wrapper.get('[data-testid="tool-filter-select"]').setValue('web_search')
    await flushPromises()
    await wrapper.get('[data-testid="team-filter-clear"]').trigger('click')
    await wrapper.get('[data-testid="tool-filter-clear"]').trigger('click')
    await flushPromises()

    expect(get).not.toHaveBeenCalled()
    expect(post).not.toHaveBeenCalled()
  })
})

describe('OrgChart multi-filter (#14608): filtered, never "no data"', () => {
  it('a team matching nobody in the hierarchy still shows the roster box, not a blank canvas', async () => {
    const wrapper = await mountOnCanvas()

    await wrapper.get('[data-testid="team-filter-select"]').setValue('t-platform')
    await flushPromises()

    // Design's roster container survives, emptied — the box is the cue, same
    // as the role lens's own unit-container precedent.
    const ids = canvasNodeIds(wrapper)
    expect(ids).toContain(`${TEAM_GROUP_PREFIX}t-design`)
    expect(ids.filter((id) => id.startsWith(`${TEAM_GROUP_PREFIX}t-design`))).toEqual([
      `${TEAM_GROUP_PREFIX}t-design`,
    ])
    // The reporting hierarchy's own unit box also survives, unaffected.
    expect(ids).toContain(`${ORG_GROUP_PREFIX}ceo`)
    expect(wrapper.find('[data-testid="canvas-filters-empty"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="role-lens-empty-canvas"]').exists()).toBe(false)
    // Platform has exactly one match (Grace), out of five people company-wide.
    expect(wrapper.get('[data-testid="team-filter-banner"]').text()).toContain('showing 1 of 5')
  })

  it('a tool matching nobody in the hierarchy still shows the tool\'s own card, not a blank canvas', async () => {
    // "jira" is carried only by "Manager" — no ungrouped person here holds
    // it, but ceo (the unit root) does, so narrow the tab to prove the card
    // survives even when the *unit* itself is filtered elsewhere. Simpler:
    // assert the card and the banner's zero count together.
    const wrapper = await mountOnCanvas()

    await wrapper.get('[data-testid="tool-filter-select"]').setValue('jira')
    await flushPromises()

    const ids = canvasNodeIds(wrapper)
    expect(ids).toContain('tool:jira')
    expect(wrapper.find('[data-testid="canvas-filters-empty"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="tool-filter-banner"]').text()).toContain('jira')
  })

  it('once team joins role, an emptied hierarchy shows the team box, never the role-only empty message', async () => {
    // A single ungrouped AGENT — an agent can never be a team member (team
    // membership keys on `users.id`), so combining its own matching role with
    // ANY team guarantees the hierarchy has zero matches, while the selected
    // team's own (unrelated, and here also empty) roster box still exists as
    // a landmark — proving the branch correctly leaves the OLD single-role
    // path once a second axis is active, rather than misreporting "no data".
    const solo = [
      {
        id: 'solo1', name: 'Solo One', title: 'lead', status: 'idle', adapter_type: 'claude',
        is_human: false, last_heartbeat: null, budget_spent: 0, budget_total: 0,
        assigned_item_count: 0, parent_id: null, children: [],
      },
    ]
    const teams = [{ id: 't-design', name: 'Design', member_user_ids: [] }]
    const wrapper = await mountOnCanvas({ people: solo, teams, tools: [], processes: [] })

    await wrapper.get('[data-testid="role-lens-select"]').setValue('lead')
    await wrapper.get('[data-testid="team-filter-select"]').setValue('t-design')
    await flushPromises()

    // Neither empty-canvas message fires — the team's own box is on screen.
    expect(wrapper.find('[data-testid="role-lens-empty-canvas"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="canvas-filters-empty"]').exists()).toBe(false)
    const ids = canvasNodeIds(wrapper)
    // Both containers survive as landmarks — Design (the selected team)
    // and the honest "not in a team" bucket solo1 itself falls into (an
    // agent can never be a real team member) — but no org-person node does.
    expect(ids.sort()).toEqual([`${TEAM_GROUP_PREFIX}__no_team__`, `${TEAM_GROUP_PREFIX}t-design`].sort())
    // The role banner still reports its own (role-only) count, unaffected by
    // team — solo1 matches "lead" on its own.
    expect(wrapper.get('[data-testid="role-lens-banner"]').text()).toContain('showing 1 of 1')
  })
})

describe('OrgChart multi-filter (#14608): clearing restores the full canvas', () => {
  it('each filter\'s own clear button resets only that axis', async () => {
    const wrapper = await mountOnCanvas()

    await wrapper.get('[data-testid="role-lens-select"]').setValue('Engineer')
    await wrapper.get('[data-testid="team-filter-select"]').setValue('t-design')
    await wrapper.get('[data-testid="tool-filter-select"]').setValue('web_search')
    await flushPromises()

    await wrapper.get('[data-testid="team-filter-clear"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="team-filter-banner"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="role-lens-banner"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="tool-filter-banner"]').exists()).toBe(true)
  })

  it('clearing every filter restores every node', async () => {
    const wrapper = await mountOnCanvas()

    await wrapper.get('[data-testid="role-lens-select"]').setValue('Engineer')
    await wrapper.get('[data-testid="team-filter-select"]').setValue('t-design')
    await wrapper.get('[data-testid="tool-filter-select"]').setValue('web_search')
    await flushPromises()

    await wrapper.get('[data-testid="role-lens-clear"]').trigger('click')
    await wrapper.get('[data-testid="team-filter-clear"]').trigger('click')
    await wrapper.get('[data-testid="tool-filter-clear"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="role-lens-banner"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="team-filter-banner"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="tool-filter-banner"]').exists()).toBe(false)
    const ids = canvasNodeIds(wrapper)
    expect(ids).toEqual(
      expect.arrayContaining(['ceo', 'dev', `user:${USER_ID_1}`, `user:${USER_ID_2}`, `user:${USER_ID_3}`]),
    )
  })
})
