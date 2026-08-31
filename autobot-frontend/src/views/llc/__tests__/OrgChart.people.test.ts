// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// GH#13938: the Org Chart is the native place to display teams and people, and
// a company has three kinds of person — agent, user, contact.
//
// These tests assert **rendered content**, never that a component mounted: each
// one names a person and fails if that person is missing from the DOM. Five
// defects have shipped in this codebase behind tests that asserted a mount or a
// shape the API never sends, so a passing mount proves nothing here.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { ref } from 'vue'
import en from '@/i18n/locales/en.json'
import ar from '@/i18n/locales/ar.json'

const get = vi.fn()
const post = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get, post }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

// Mutable so a test can exercise the "no company selected" path — the guard
// that stops the People tab requesting /api/llc/contacts/undefined/involved. A real
// `ref`, not a `{ value }` look-alike (#13940): `companyId` is now also
// forwarded as a typed `string` prop to `CanvasNodeSidebar`, and only an
// actual `Ref` auto-unwraps in the template.
const companyRef = ref<string | null>('c1')
vi.mock('@/composables/llc/useLlcCompanyContext', () => ({
  useLlcCompanyContext: () => ({
    companyId: companyRef,
    resolveCompanyId: () => Promise.resolve(companyRef.value),
  }),
}))

import OrgChart from '../OrgChart.vue'
import OrgTreeNode from '../OrgTreeNode.vue'
import WorkflowCanvas from '@/components/workflow/WorkflowCanvas.vue'

const AGENT_NAME = 'Ada'
const USER_NAME = 'Grace'
const CONTACT_NAME = 'Hedy Lamarr'
const USER_ID = '11111111-1111-1111-1111-111111111111'
const TEAM_NAME = 'Platform'

/** The org chart as the backend composes it: a hired agent and a member. */
const ORG_NODES = [
  {
    id: 'ceo',
    node_id: 'ceo-uuid',
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
    children: [],
  },
  {
    // `_compose_human_nodes` namespaces a person's id as `user:<uuid>` and keeps
    // the raw user id in `node_id` (#13936).
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
]

/** A contact as `GET /api/llc/contacts/{company_id}/involved` returns it (#13969, #13998). */
const CONTACTS = [
  {
    id: 'c0ffee00-0000-0000-0000-000000000001',
    company_id: 'c1',
    full_name: CONTACT_NAME,
    email: 'hedy@supplier.example',
    phone: null,
    role_title: 'Accounts Payable at Acme Supplies',
    notes: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
]

const TEAMS = [{ id: 't1', name: TEAM_NAME, member_user_ids: [USER_ID] }]

type Fixture = {
  nodes?: unknown[]
  contacts?: unknown[]
  /** #13998: people the department carries with no role to explain them. */
  unassignedContacts?: unknown[]
  /** A response that is not the two-array shape at all. */
  malformedContacts?: boolean
  /** Only `unassigned` is unreadable; `with_role` is fine. */
  halfMalformedContacts?: boolean
  teams?: unknown[]
  contactsFail?: boolean
  teamsFail?: boolean
  rollupFail?: boolean
}

function mockApi({
  nodes = ORG_NODES,
  contacts = CONTACTS,
  unassignedContacts = [],
  malformedContacts = false,
  halfMalformedContacts = false,
  teams = TEAMS,
  contactsFail = false,
  teamsFail = false,
  rollupFail = false,
}: Fixture = {}) {
  get.mockImplementation((url: string) => {
    if (url === '/api/llc/companies/c1/org-chart') {
      return Promise.resolve({ nodes: structuredClone(nodes) })
    }
    // #13942: OrgChart also loads the executor rollup on mount, independent
    // of the People tab — every fixture in this file must answer it.
    if (url === '/api/llc/companies/c1/work-items/executor-rollup') {
      return rollupFail
        ? Promise.reject(new Error('rollup unavailable'))
        : Promise.resolve({ cells: [] })
    }
    if (url === '/api/llc/contacts/c1/involved') {
      // #13998: the People tab reads a department's people as two groups —
      // those a role explains, and those carried from before the directory was
      // shared. `unassignedContacts` lets a test put a person in the second.
      if (contactsFail) return Promise.reject(new Error('contacts unavailable'))
      if (malformedContacts) return Promise.resolve({ detail: 'not the expected shape' })
      if (halfMalformedContacts) {
        return Promise.resolve({ with_role: structuredClone(contacts), unassigned: null })
      }
      return Promise.resolve({
        with_role: structuredClone(contacts),
        unassigned: structuredClone(unassignedContacts),
      })
    }
    if (url === '/api/llc/companies/c1/teams') {
      return teamsFail
        ? Promise.reject(new Error('teams unavailable'))
        : Promise.resolve({ teams: structuredClone(teams) })
    }
    throw new Error(`unexpected GET ${url}`)
  })
}

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages: { en, ar },
})

async function mountChart(fixture?: Fixture) {
  if (fixture) mockApi(fixture)
  const wrapper = mount(OrgChart, { global: { plugins: [i18n], stubs: { HireAgentModal: true } } })
  await flushPromises()
  return wrapper
}

/** Open the People list — the third view mode, beside tree and canvas. */
async function mountPeople(fixture?: Fixture) {
  mockApi(fixture)
  const wrapper = await mountChart()
  await wrapper.get('[data-testid="org-view-people"]').trigger('click')
  await flushPromises()
  return wrapper
}

/** The rendered row for a person, found by the name the user reads. */
function personRow(wrapper: Awaited<ReturnType<typeof mountChart>>, name: string) {
  return wrapper.findAll('[data-testid^="org-person-"]').find((row) => row.text().includes(name))
}

beforeEach(() => {
  get.mockReset()
  post.mockReset()
  post.mockResolvedValue({})
  i18n.global.locale.value = 'en'
  mockApi()
})

describe('Org Chart People list shows all three kinds (#13938)', () => {
  it('renders the agent, the user and the contact, each with its own kind label', async () => {
    const wrapper = await mountPeople()
    const text = wrapper.text()

    // Every kind must actually appear — this fails if any one is dropped.
    expect(text).toContain(AGENT_NAME)
    expect(text).toContain(USER_NAME)
    expect(text).toContain(CONTACT_NAME)

    expect(personRow(wrapper, AGENT_NAME)?.text()).toContain(en.llc.orgChart.peopleKind.agent)
    expect(personRow(wrapper, USER_NAME)?.text()).toContain(en.llc.orgChart.peopleKind.user)
    expect(personRow(wrapper, CONTACT_NAME)?.text()).toContain(en.llc.orgChart.peopleKind.contact)
  })

  it('distinguishes the three kinds with three different token classes', async () => {
    const wrapper = await mountPeople()

    const badgeClass = (name: string) =>
      personRow(wrapper, name)!.get('[data-testid^="org-person-kind-"]').classes().join(' ')

    const agent = badgeClass(AGENT_NAME)
    const user = badgeClass(USER_NAME)
    const contact = badgeClass(CONTACT_NAME)

    expect(new Set([agent, user, contact]).size).toBe(3)
    // Design tokens only — a literal colour would never appear as a token class.
    for (const cls of [agent, user, contact]) expect(cls).toMatch(/autobot-/)
  })

  it("shows the contact's process channel, which is how a contact is reached", async () => {
    const wrapper = await mountPeople()

    expect(personRow(wrapper, CONTACT_NAME)?.text()).toContain('hedy@supplier.example')
    expect(personRow(wrapper, CONTACT_NAME)?.text()).toContain('Accounts Payable at Acme Supplies')
  })

  it('states that contacts are not in the reporting hierarchy', async () => {
    const wrapper = await mountPeople()

    expect(wrapper.get('[data-testid="org-people-contact-note"]').text()).toBe(
      en.llc.orgChart.peopleContactNotInHierarchy,
    )
  })

  it('counts each kind in the legend', async () => {
    const wrapper = await mountPeople()

    expect(wrapper.get('[data-testid="org-people-legend-agent"]').text()).toContain('1')
    expect(wrapper.get('[data-testid="org-people-legend-user"]').text()).toContain('1')
    expect(wrapper.get('[data-testid="org-people-legend-contact"]').text()).toContain('1')
  })

  it('renders the kind labels of an RTL locale, not English fallbacks', async () => {
    const wrapper = await mountPeople()
    i18n.global.locale.value = 'ar'
    await flushPromises()

    expect(wrapper.text()).toContain(ar.llc.orgChart.peopleKind.contact)
    expect(wrapper.text()).toContain(ar.llc.orgChart.peopleNoTeam)
    expect(wrapper.text()).not.toContain(en.llc.orgChart.peopleKind.contact)
  })
})

// `loadPeopleSources` documents an invariant — "a teams endpoint failure must
// not blank the people" — and uses Promise.allSettled to keep a partial answer
// partial. That branch was the only uncovered code in this change, i.e. a
// documented promise with nothing holding it. #14064 is the same failure class:
// a load failure that renders as a legitimately empty list.
describe('A partial source failure stays partial (#13938)', () => {
  it('still renders every person when the teams endpoint fails', async () => {
    const wrapper = await mountPeople({ teamsFail: true })
    const text = wrapper.text()

    expect(text).toContain(AGENT_NAME)
    expect(text).toContain(USER_NAME)
    expect(text).toContain(CONTACT_NAME)
    // The team grouping is what is lost — the people are not.
    expect(text).not.toContain(TEAM_NAME)

    // …and the UI must not turn "we did not get an answer" into the positive
    // claim "no teams are defined for this company". That sentence is a fact
    // about the company; we only know it when the request actually succeeded.
    expect(wrapper.find('[data-testid="org-people-no-teams"]').exists()).toBe(false)
    expect(text).not.toContain(en.llc.orgChart.peopleNoTeamsDefined)
    expect(wrapper.find('[data-testid="org-people-teams-unavailable"]').exists()).toBe(true)
  })

  it('says the people could not be loaded, not that the company has none', async () => {
    // The company #13969 was built for: its only people are contacts. If that
    // request fails, "This company has no people yet." is a false statement
    // indistinguishable from the truth — the exact shape of #14064.
    const wrapper = await mountPeople({ nodes: [], contactsFail: true })

    expect(wrapper.find('[data-testid="org-people-empty"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain(en.llc.orgChart.peopleEmpty)
    expect(wrapper.find('[data-testid="org-people-unavailable"]').exists()).toBe(true)
  })

  it('retries on re-entry after a failure instead of caching the gap', async () => {
    const wrapper = await mountPeople({ teamsFail: true })
    const teamCalls = () =>
      get.mock.calls.filter(([url]) => String(url).includes('/teams')).length
    expect(teamCalls()).toBe(1)

    // A complete answer is cached; a partial one must not be, or the company
    // keeps its degraded view until a full page reload.
    mockApi()
    await wrapper.get('[data-testid="org-view-tree"]').trigger('click')
    await wrapper.get('[data-testid="org-view-people"]').trigger('click')
    await flushPromises()

    expect(teamCalls()).toBe(2)
    expect(wrapper.text()).toContain(TEAM_NAME)
  })

  it('still renders the team grouping when the contacts endpoint fails', async () => {
    const wrapper = await mountPeople({ contactsFail: true })
    const text = wrapper.text()

    expect(text).toContain(USER_NAME)
    expect(text).toContain(TEAM_NAME)
    expect(text).not.toContain(CONTACT_NAME)
  })

  it('requests nothing when no company is selected', async () => {
    companyRef.value = null
    try {
      const wrapper = await mountPeople()
      await wrapper.get('[data-testid="org-view-people"]').trigger('click')
      await flushPromises()

      // Without the guard these become /api/llc/contacts/null/involved.
      const peopleCalls = get.mock.calls.filter(([url]) =>
        String(url).includes('/contacts/') || String(url).includes('/teams'),
      )
      expect(peopleCalls).toEqual([])
    } finally {
      companyRef.value = 'c1'
    }
  })

  it('fetches the people sources once, however often the tab is re-entered', async () => {
    const wrapper = await mountPeople()
    const countContactCalls = () =>
      get.mock.calls.filter(([url]) => url === '/api/llc/contacts/c1/involved').length
    expect(countContactCalls()).toBe(1)

    // Leave and come back twice — the guard must hold, or every tab switch
    // re-fetches and the list flickers.
    for (const mode of ['tree', 'people', 'canvas', 'people']) {
      await wrapper.get(`[data-testid="org-view-${mode}"]`).trigger('click')
      await flushPromises()
    }
    expect(countContactCalls()).toBe(1)
  })
})

describe('Contacts stay out of the reporting tree (#13938)', () => {
  it('never renders a contact in the nested tree', async () => {
    mockApi()
    const wrapper = await mountChart()
    // Visit the People list first so the contacts are loaded, then go back.
    await wrapper.get('[data-testid="org-view-people"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="org-view-tree"]').trigger('click')
    await flushPromises()

    const treeText = wrapper
      .findAllComponents(OrgTreeNode)
      .map((node) => node.text())
      .join(' ')
    expect(treeText).toContain(AGENT_NAME)
    expect(treeText).toContain(USER_NAME)
    expect(treeText).not.toContain(CONTACT_NAME)
  })

  it('never puts a contact on the canvas', async () => {
    mockApi()
    const wrapper = await mountChart()
    await wrapper.get('[data-testid="org-view-people"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="org-view-canvas"]').trigger('click')
    await flushPromises()

    const names = wrapper
      .findComponent(WorkflowCanvas)
      .props('nodes')
      .map((node: { data?: { label?: string } }) => node.data?.label ?? '')
    expect(names.join(' ')).not.toContain(CONTACT_NAME)
  })

  it('offers no detail drawer for a contact — there is no hierarchy node to open', async () => {
    const wrapper = await mountPeople()

    // #14603: a contact row does get a button now (the inline edit
    // affordance), so "any button" would falsely pass here regardless of the
    // drawer. Scoped to the specific testid the drawer-opening button carries.
    expect(personRow(wrapper, USER_NAME)!.find('[data-testid^="org-person-open-"]').exists()).toBe(
      true,
    )
    expect(
      personRow(wrapper, CONTACT_NAME)!.find('[data-testid^="org-person-open-"]').exists(),
    ).toBe(false)
  })

  it('opens the same drawer the tree opens when a hierarchy member is clicked', async () => {
    const wrapper = await mountPeople()

    await personRow(wrapper, USER_NAME)!.get('button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain(en.llc.orgChart.personDetail)
    expect(wrapper.text()).toContain(USER_NAME)
  })
})

describe('Team grouping is honest about the data that exists (#13938)', () => {
  it('groups the user under the team that claims them', async () => {
    const wrapper = await mountPeople()

    const team = wrapper.get('[data-testid="org-people-group-t1"]')
    expect(team.text()).toContain(TEAM_NAME)
    expect(team.text()).toContain(USER_NAME)
  })

  it('puts agents and contacts in the "not in a team" bucket, never a fabricated team', async () => {
    const wrapper = await mountPeople()

    const ungrouped = wrapper.get('[data-testid="org-people-group-__no_team__"]')
    expect(ungrouped.text()).toContain(en.llc.orgChart.peopleNoTeam)
    expect(ungrouped.text()).toContain(AGENT_NAME)
    expect(ungrouped.text()).toContain(CONTACT_NAME)
    expect(ungrouped.text()).not.toContain(USER_NAME)
  })

  it('renders an honest empty state — and no group headers — when the company has no team', async () => {
    const wrapper = await mountPeople({ teams: [] })

    expect(wrapper.get('[data-testid="org-people-no-teams"]').text()).toBe(
      en.llc.orgChart.peopleNoTeamsDefined,
    )
    expect(wrapper.find('h3').exists()).toBe(false)
    // Everyone is still listed — an absent grouping never hides a person.
    for (const name of [AGENT_NAME, USER_NAME, CONTACT_NAME]) {
      expect(wrapper.text()).toContain(name)
    }
  })

  it('shows an empty team as empty rather than dropping it', async () => {
    const wrapper = await mountPeople({
      teams: [{ id: 't2', name: 'Marketing', member_user_ids: [] }],
    })

    const team = wrapper.get('[data-testid="org-people-group-t2"]')
    expect(team.text()).toContain('Marketing')
    expect(team.text()).toContain(en.llc.orgChart.peopleTeamEmpty)
  })
})

describe('People list loading behaviour (#13938)', () => {
  it('does not fetch contacts or teams until the People list is opened', async () => {
    mockApi()
    const wrapper = await mountChart()

    // #13942: mount now issues two requests — the tree and the (independent,
    // always-on) executor rollup — neither of which touches contacts/teams.
    expect(get).toHaveBeenCalledTimes(2)
    expect(get).toHaveBeenCalledWith('/api/llc/companies/c1/org-chart')
    expect(get).toHaveBeenCalledWith('/api/llc/companies/c1/work-items/executor-rollup')

    await wrapper.get('[data-testid="org-view-people"]').trigger('click')
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/api/llc/contacts/c1/involved')
    expect(get).toHaveBeenCalledWith('/api/llc/companies/c1/teams')
  })

  it('still lists agents and users when the contacts request fails', async () => {
    const wrapper = await mountPeople({ contactsFail: true })

    expect(wrapper.text()).toContain(AGENT_NAME)
    expect(wrapper.text()).toContain(USER_NAME)
    expect(wrapper.text()).not.toContain(CONTACT_NAME)
  })

  it('lists a company that has contacts and an empty hierarchy', async () => {
    // An empty org chart is not an empty company: the hierarchy short-circuit
    // used to report "no people" over a list that has some.
    const wrapper = await mountPeople({ nodes: [] })

    expect(wrapper.text()).toContain(CONTACT_NAME)
    expect(wrapper.text()).not.toContain(en.llc.orgChart.empty)
  })

  it('reports an genuinely empty company with the People empty state', async () => {
    const wrapper = await mountPeople({ nodes: [], contacts: [], teams: [] })

    expect(wrapper.get('[data-testid="org-people-empty"]').text()).toBe(en.llc.orgChart.peopleEmpty)
  })
})

// #13942: the panel distinguishes "no work items" from "we could not ask".
// A rollup reading 0 unassigned when the request failed is the worst version of
// #14064 — it is a number a reader would act on. The failure branch was the only
// uncovered code in this change, i.e. the honest-failure behaviour was asserted
// by nobody.
describe('the executor rollup never reports zero when it failed to load (#13942)', () => {
  it('shows the unavailable state instead of an all-zero matrix', async () => {
    const wrapper = await mountChart({ rollupFail: true })

    expect(wrapper.find('[data-testid="executor-rollup-unavailable"]').exists()).toBe(true)
    // Nothing on screen may present a count the request never returned — not the
    // table, not the legend, not the total line.
    expect(wrapper.find('[data-testid="executor-rollup-table"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="executor-rollup-legend"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="executor-rollup-total"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="executor-rollup-empty"]').exists()).toBe(false)
  })

  it('reports an answered-but-empty rollup as empty, not as unavailable', async () => {
    // The case that must stay distinguishable: the request succeeded and the
    // company genuinely has no work items.
    const wrapper = await mountChart()

    expect(wrapper.find('[data-testid="executor-rollup-unavailable"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="executor-rollup-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="executor-rollup-total"]').exists()).toBe(true)
  })

  it('labels a contact no role explains, and only that one (#13998)', async () => {
    // The two groups must stay distinguishable in the UI. Merging them would
    // assert an involvement nobody recorded; hiding the second would make
    // people vanish from a department already using them.
    const wrapper = await mountPeople({
      contacts: [CONTACTS[0]],
      unassignedContacts: [
        { id: 'legacy-1', full_name: 'Hedy Lamarr', email: null, role_title: null },
      ],
    })

    expect(wrapper.text()).toContain('Hedy Lamarr')
    expect(wrapper.find('[data-testid="org-person-unassigned-contact:legacy-1"]').exists()).toBe(
      true,
    )
    // The role-explained contact carries no label.
    expect(
      wrapper.find(`[data-testid="org-person-unassigned-contact:${CONTACTS[0].id}"]`).exists(),
    ).toBe(false)
  })

  it('treats a malformed involved response as no contacts, not a crash (#13998)', async () => {
    // The endpoint returns two arrays. A response shaped differently — an older
    // backend, a proxy returning an error body with a 200, a contract change —
    // must yield an empty list rather than throwing inside the People tab or
    // spreading a non-iterable. The teams half must still render.
    const wrapper = await mountPeople({ malformedContacts: true })

    // The teams half is loaded AFTER contacts in the same function, so its
    // presence proves the contacts block completed rather than threw. Without
    // this the test passes on a crash: a thrown spread leaves `contacts` empty,
    // which satisfies the "no contact rendered" assertion below for the wrong
    // reason. Verified by mutation.
    expect(wrapper.text()).toContain(TEAM_NAME)
    expect(wrapper.text()).toContain(AGENT_NAME)
    // ...and no contact is invented from a response that did not contain any.
    expect(
      wrapper
        .findAll('[data-testid^="org-person-"]')
        .some((row) => row.text().includes(CONTACT_NAME)),
    ).toBe(false)
  })

  it('keeps the people it did get when only one group is malformed', async () => {
    // A partial answer is still an answer: dropping the valid half because the
    // other is unreadable would hide people the department genuinely has.
    const wrapper = await mountPeople({ halfMalformedContacts: true })

    // `with_role` was readable, so its people are shown even though the other
    // group was not.
    expect(wrapper.text()).toContain(CONTACT_NAME)
  })
})
