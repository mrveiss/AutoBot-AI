// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// GH#14596: teams on the Company OS canvas. `org-group` (`isOrgUnit`) answers
// "who reports to whom" — a team answers "who works together", and until now
// it existed only as a grouping header in the People tab. These tests pin:
//
//  * a team renders as its own container, in a different id namespace than a
//    reporting-unit container — never the same box under two names;
//  * a person on no team is still a first-class, visible, labelled canvas
//    node — never silently dropped;
//  * a failed teams fetch reads as "could not load", never as "this company
//    has no teams" (#14064, #13617, #14556 — the same defect three times);
//  * the team label renders through an RTL locale, not an English fallback.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ar from '@/i18n/locales/ar.json'

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

vi.mock('@/composables/llc/useLlcCompanyContext', () => ({
  useLlcCompanyContext: () => ({
    companyId: { value: 'c1' },
    resolveCompanyId: () => Promise.resolve('c1'),
  }),
}))

import OrgChart from '../OrgChart.vue'
import WorkflowCanvas from '@/components/workflow/WorkflowCanvas.vue'
import { ORG_GROUP_PREFIX, TEAM_GROUP_PREFIX, teamMemberOrgNodeId } from '@/composables/llc/orgCanvasGraph'

const AGENT_NAME = 'Ada'
const USER_NAME = 'Grace'
const SOLO_NAME = 'Hana'
const USER_ID = '11111111-1111-1111-1111-111111111111'
const SOLO_ID = '22222222-2222-2222-2222-222222222222'
const TEAM_NAME = 'Platform'

/** A reporting unit (`ceo` has a report) plus two bare members (#13994). */
const ORG_NODES = [
  {
    id: 'ceo',
    name: AGENT_NAME,
    title: 'CEO',
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
        title: 'worker',
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
    id: `user:${USER_ID}`,
    node_id: USER_ID,
    name: USER_NAME,
    title: 'lead',
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
    id: `user:${SOLO_ID}`,
    node_id: SOLO_ID,
    name: SOLO_NAME,
    title: 'member',
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

const TEAMS = [{ id: 't1', name: TEAM_NAME, member_user_ids: [USER_ID] }]

type Fixture = {
  teams?: unknown[]
  teamsFail?: boolean
}

function mockApi({ teams = TEAMS, teamsFail = false }: Fixture = {}) {
  get.mockImplementation((url: string) => {
    if (url === '/api/llc/companies/c1/org-chart') {
      return Promise.resolve({ nodes: structuredClone(ORG_NODES) })
    }
    if (url === '/api/llc/companies/c1/work-items/executor-rollup') {
      return Promise.resolve({ cells: [] })
    }
    if (url === '/api/llc/companies/c1/process-nodes') {
      return Promise.resolve({ nodes: [] })
    }
    if (url === '/api/llc/roles/c1') {
      return Promise.resolve([])
    }
    if (url === '/api/llc/contacts/c1/involved') {
      return Promise.resolve({ with_role: [], unassigned: [] })
    }
    if (url === '/api/llc/companies/c1/teams') {
      return teamsFail
        ? Promise.reject(new Error('teams unavailable'))
        : Promise.resolve({ teams: structuredClone(teams) })
    }
    throw new Error(`unexpected GET ${url}`)
  })
}

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en, ar } })
}

// #14860: the default is ONE shared instance. Seven of this file's nine mounts
// never touch the locale, and each was re-ingesting the ~400KB `en` and `ar`
// bundles. The two RTL cases below deliberately mutate
// `i18n.global.locale.value`, so they keep calling makeI18n() and pass their own
// instance in — a mutated instance must never reach the next test.
const sharedI18n = makeI18n()

async function mountOnCanvas(fixture?: Fixture, i18n = sharedI18n) {
  mockApi(fixture)
  const wrapper = mount(OrgChart, { global: { plugins: [i18n], stubs: { HireAgentModal: true } } })
  await flushPromises()
  await wrapper.get('[data-testid="org-view-canvas"]').trigger('click')
  await flushPromises()
  return { wrapper, i18n }
}

function canvasNodeIds(wrapper: Awaited<ReturnType<typeof mountOnCanvas>>['wrapper']): string[] {
  return wrapper.findComponent(WorkflowCanvas).props('nodes').map((n: { id: string }) => n.id)
}

beforeEach(() => {
  get.mockReset()
  post.mockReset()
  push.mockReset()
  post.mockResolvedValue({})
})

describe('Teams on the canvas are a first-class grouping (#14596)', () => {
  it('draws a team container in a different id namespace than the reporting-unit container', async () => {
    const { wrapper } = await mountOnCanvas()
    const ids = canvasNodeIds(wrapper)

    const unitContainer = ids.find((id) => id.startsWith(ORG_GROUP_PREFIX))
    const teamContainer = ids.find((id) => id.startsWith(TEAM_GROUP_PREFIX))

    expect(unitContainer).toBe(`${ORG_GROUP_PREFIX}ceo`)
    expect(teamContainer).toBe(`${TEAM_GROUP_PREFIX}t1`)
    // Never the same id under two prefixes — the discriminator a mutation of
    // either prefix constant would collapse.
    expect(unitContainer).not.toBe(teamContainer)
  })

  it("labels the team container with the team's own name, distinct from the unit's caption", async () => {
    const { wrapper } = await mountOnCanvas()
    const nodes = wrapper.findComponent(WorkflowCanvas).props('nodes') as {
      id: string
      data: { label?: string }
    }[]

    const teamContainer = nodes.find((n) => n.id === `${TEAM_GROUP_PREFIX}t1`)!
    const unitContainer = nodes.find((n) => n.id === `${ORG_GROUP_PREFIX}ceo`)!

    expect(teamContainer.data.label).toBe(en.llc.orgChart.canvasTeam.replace('{name}', TEAM_NAME))
    expect(unitContainer.data.label).toBe(en.llc.orgChart.canvasUnit.replace('{name}', AGENT_NAME))
  })

  it('duplicates a team member as its own canvas node, resolving back to the same real person', async () => {
    const { wrapper } = await mountOnCanvas()
    const ids = canvasNodeIds(wrapper)

    const graceInTeam = ids.find(
      (id) => id.startsWith(`${TEAM_GROUP_PREFIX}t1`) && teamMemberOrgNodeId(id) === `user:${USER_ID}`,
    )
    expect(graceInTeam).toBeDefined()
    // The reporting-hierarchy copy of the same person is also still there —
    // the team view adds a node, it does not replace one.
    expect(ids).toContain(`user:${USER_ID}`)
  })

  it('opens the same drawer for a team roster click as for the reporting-hierarchy node', async () => {
    const { wrapper } = await mountOnCanvas()
    const ids = canvasNodeIds(wrapper)
    const graceInTeam = ids.find(
      (id) => id.startsWith(`${TEAM_GROUP_PREFIX}t1`) && teamMemberOrgNodeId(id) === `user:${USER_ID}`,
    )!

    await wrapper.findComponent(WorkflowCanvas).vm.$emit('node-selected', graceInTeam)
    await flushPromises()

    expect(wrapper.text()).toContain(USER_NAME)
    expect(push).not.toHaveBeenCalled()
  })

  it('shows a person on no team, unmissed, in the honest ungrouped bucket', async () => {
    const { wrapper } = await mountOnCanvas()
    const ids = canvasNodeIds(wrapper)

    const ungroupedContainer = ids.find((id) => id === `${TEAM_GROUP_PREFIX}__no_team__`)
    const hanaOnCanvas = ids.find(
      (id) =>
        id.startsWith(`${TEAM_GROUP_PREFIX}__no_team__`) &&
        teamMemberOrgNodeId(id) === `user:${SOLO_ID}`,
    )

    expect(ungroupedContainer).toBeDefined()
    expect(hanaOnCanvas).toBeDefined()
  })
})

describe('An honest "no teams" reads differently from a failed fetch (#14596, #14064)', () => {
  it('says the company has none, once the teams request has actually answered that', async () => {
    const { wrapper } = await mountOnCanvas({ teams: [] })

    expect(wrapper.get('[data-testid="canvas-no-teams"]').text()).toBe(
      en.llc.orgChart.peopleNoTeamsDefined,
    )
    expect(wrapper.find('[data-testid="canvas-teams-unavailable"]').exists()).toBe(false)
    // Paired positive: the canvas is not merely blank — the reporting
    // hierarchy still rendered, so an empty team section here is a fact
    // about teams, not a crashed render coincidentally lacking a banner.
    expect(canvasNodeIds(wrapper)).toContain(`${ORG_GROUP_PREFIX}ceo`)
    expect(canvasNodeIds(wrapper).some((id) => id.startsWith(TEAM_GROUP_PREFIX))).toBe(false)
  })

  it('says the teams could not be loaded, never that the company has none', async () => {
    const { wrapper } = await mountOnCanvas({ teamsFail: true })

    expect(wrapper.get('[data-testid="canvas-teams-unavailable"]').text()).toBe(
      en.llc.orgChart.peopleTeamsUnavailable,
    )
    expect(wrapper.find('[data-testid="canvas-no-teams"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain(en.llc.orgChart.peopleNoTeamsDefined)
    // Paired positive, same reasoning as above: the org chart itself is
    // still intact — only the team grouping is the part that failed.
    expect(canvasNodeIds(wrapper)).toContain(`${ORG_GROUP_PREFIX}ceo`)
    expect(canvasNodeIds(wrapper)).toContain(`user:${USER_ID}`)
  })
})

describe('Teams read correctly in an RTL locale (#14596)', () => {
  it('labels the team container in Arabic, not with the English fallback', async () => {
    const i18n = makeI18n()
    const { wrapper } = await mountOnCanvas(undefined, i18n)
    i18n.global.locale.value = 'ar'
    await flushPromises()

    const nodes = wrapper.findComponent(WorkflowCanvas).props('nodes') as {
      id: string
      data: { label?: string }
    }[]
    const teamContainer = nodes.find((n) => n.id === `${TEAM_GROUP_PREFIX}t1`)!

    expect(teamContainer.data.label).toBe(ar.llc.orgChart.canvasTeam.replace('{name}', TEAM_NAME))
    expect(teamContainer.data.label).not.toBe(en.llc.orgChart.canvasTeam.replace('{name}', TEAM_NAME))
  })

  it("labels the 'not in a team' bucket in Arabic when the locale is RTL", async () => {
    const i18n = makeI18n()
    const { wrapper } = await mountOnCanvas(undefined, i18n)
    i18n.global.locale.value = 'ar'
    await flushPromises()

    const nodes = wrapper.findComponent(WorkflowCanvas).props('nodes') as {
      id: string
      data: { label?: string }
    }[]
    const ungrouped = nodes.find((n) => n.id === `${TEAM_GROUP_PREFIX}__no_team__`)!

    expect(ungrouped.data.label).toBe(ar.llc.orgChart.peopleNoTeam)
  })
})
