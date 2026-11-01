// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #18245: the Teams screen says loading, empty, couldn't-read and not-available apart, names members from
// the company's member list, and every write goes to the company shown with the server's refusal on screen.

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { defineComponent, h, reactive } from 'vue'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
const post = vi.fn()
const del = vi.fn()
const route = reactive({ params: { companyId: 'coA' } })

vi.mock('vue-router', () => ({ useRoute: () => route }))
vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get, post, delete: del }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import TeamsView from '../TeamsView.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

const MEMBERS = [
  { user_id: 'u1', display_name: 'Jane Doe', role: 'owner', is_active: true },
  { user_id: 'u2', display_name: 'Alex Smith', role: 'member', is_active: true },
  { user_id: 'u3', display_name: 'Alex Smith', role: 'guest', is_active: true },
  { user_id: 'u4', display_name: 'Left Person', role: 'member', is_active: false },
]
const TEAMS = { teams: [{ id: 't1', name: 'Platform', member_user_ids: ['u1', 'u2'] }, { id: 't2', name: 'Empty team', member_user_ids: [] }] }

// The kit select needs reka-ui; a native select with the same v-model contract stands in for it here.
const SelectStub = defineComponent({
  props: { options: { type: Array, default: () => [] }, modelValue: { type: String, default: '' }, label: String },
  emits: ['update:modelValue'],
  setup(p, { emit }) {
    return () =>
      h('select', { 'data-testid': 'candidate', 'aria-label': p.label, value: p.modelValue, onChange: (e: Event) => emit('update:modelValue', (e.target as HTMLSelectElement).value) },
        (p.options as { value: string; label: string }[]).map((o) => h('option', { value: o.value }, o.label)))
  },
})

function reply(teams: unknown, members: unknown = MEMBERS) {
  get.mockImplementation((url: string) => {
    const out = url.endsWith('/teams') ? teams : members
    return out instanceof Error ? Promise.reject(out) : Promise.resolve(out)
  })
}
const httpError = (status: number) => Object.assign(new Error(`http ${status}`), { status })

let wrapper: VueWrapper
async function show(): Promise<VueWrapper> {
  wrapper = mount(TeamsView, { attachTo: document.body, global: { plugins: [i18n], stubs: { BaseSelectMenu: SelectStub } } })
  await flushPromises()
  return wrapper
}
const byId = (id: string) => document.body.querySelector<HTMLElement>(`[data-testid="${id}"]`)
const click = async (el: Element | null) => { (el as HTMLElement).click(); await flushPromises() }
const buttonNamed = (text: string) => [...document.body.querySelectorAll('button')].find((b) => b.textContent?.trim() === text) ?? null

describe('TeamsView (#18245)', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset().mockResolvedValue({})
    del.mockReset().mockResolvedValue({})
    route.params.companyId = 'coA'
  })
  afterEach(() => wrapper?.unmount())

  it('shows an honest loading state until the first answer', async () => {
    get.mockReturnValue(new Promise(() => {}))
    wrapper = mount(TeamsView, { attachTo: document.body, global: { plugins: [i18n], stubs: { BaseSelectMenu: SelectStub } } })
    await flushPromises()
    expect(byId('teams-loading')?.textContent).toContain(en.llcTeams.loading)
    expect(byId('teams-empty')).toBeNull()
    expect(byId('teams-create')).toBeNull()
  })

  it('reads the company-scoped teams and members routes', async () => {
    reply(TEAMS)
    await show()
    expect(get).toHaveBeenCalledWith('/api/llc/companies/coA/teams')
    expect(get).toHaveBeenCalledWith('/api/llc/companies/coA/members')
    expect(byId('teams-table')?.textContent).toContain('Platform')
  })

  it('says there are no teams, apart from a failed read', async () => {
    reply({ teams: [] })
    await show()
    expect(byId('teams-empty')?.textContent).toContain(en.llcTeams.empty)
    expect(byId('teams-failed')).toBeNull()
    expect(byId('teams-create')).not.toBeNull()
  })

  it('says it could not read the teams, offers a retry, and never says "no teams"', async () => {
    reply(httpError(500))
    await show()
    expect(byId('teams-failed')?.textContent).toContain(en.llcTeams.loadError)
    expect(byId('teams-empty')).toBeNull()
    expect(byId('teams-create')).toBeNull()
    reply(TEAMS)
    await click(byId('teams-retry'))
    expect(byId('teams-failed')).toBeNull()
    expect(byId('teams-table')?.textContent).toContain('Platform')
  })

  it.each([403, 404])('says teams are not available when the server answers %i', async (status) => {
    reply(httpError(status))
    await show()
    expect(byId('teams-unavailable')?.textContent).toContain(en.llcTeams.unavailable)
    expect(byId('teams-failed')).toBeNull()
  })

  it('names team members from the member list and tells two people with one name apart by role', async () => {
    reply({ teams: [{ id: 't1', name: 'Platform', member_user_ids: ['u2', 'u3'] }] })
    await show()
    await click(buttonNamed(en.llcTeams.manage))
    const text = byId('team-members')?.textContent ?? ''
    expect(text.match(/Alex Smith/g)).toHaveLength(2)
    expect(text).toContain('member')
    expect(text).toContain('guest')
  })

  it('shows members without invented names when the member list cannot be read', async () => {
    reply(TEAMS, httpError(500))
    await show()
    await click(buttonNamed(en.llcTeams.manage))
    expect(byId('teams-names-error')?.textContent).toContain(en.llcTeams.namesError)
    expect(byId('team-members')?.textContent).toContain(en.llcTeams.unknownMember)
  })

  it('offers only active people who are not on the team, and says when nobody is left', async () => {
    reply(TEAMS)
    await show()
    await click(buttonNamed(en.llcTeams.manage))
    const options = [...(byId('candidate')?.querySelectorAll('option') ?? [])].map((o) => o.value)
    expect(options).toEqual(['u3'])
  })

  it('says everyone is already on the team when nobody is left to add', async () => {
    reply({ teams: [{ id: 't1', name: 'Platform', member_user_ids: ['u1', 'u2', 'u3'] }] })
    await show()
    await click(buttonNamed(en.llcTeams.manage))
    expect(byId('team-no-candidates')?.textContent).toContain(en.llcTeams.noCandidates)
    expect(byId('candidate')).toBeNull()
  })

  it('adds a member to the team of the company shown, then re-reads', async () => {
    reply(TEAMS)
    await show()
    await click(buttonNamed(en.llcTeams.manage))
    const select = byId('candidate') as HTMLSelectElement
    select.value = 'u3'
    select.dispatchEvent(new Event('change'))
    await flushPromises()
    get.mockClear()
    await click(byId('team-add-member'))
    expect(post).toHaveBeenCalledWith('/api/user-management/teams/t1/members/u3', undefined, { headers: { 'X-Organization-Id': 'coA' } })
    expect(get).toHaveBeenCalledWith('/api/llc/companies/coA/teams')
  })

  it('removes a member from the team', async () => {
    reply(TEAMS)
    await show()
    await click(buttonNamed(en.llcTeams.manage))
    await click(document.body.querySelector('[data-testid="team-remove-member"]'))
    expect(del).toHaveBeenCalledWith('/api/user-management/teams/t1/members/u1', { headers: { 'X-Organization-Id': 'coA' } })
  })

  it('creates a team with the trimmed name for the company shown', async () => {
    reply({ teams: [] })
    await show()
    await click(byId('teams-create'))
    const input = document.body.querySelector('input') as HTMLInputElement
    input.value = '  Growth  '
    input.dispatchEvent(new Event('input'))
    await flushPromises()
    await click(byId('teams-create-confirm'))
    expect(post).toHaveBeenCalledWith('/api/user-management/teams', { name: 'Growth' }, { headers: { 'X-Organization-Id': 'coA' } })
    expect(byId('teams-create-confirm')).toBeNull()
  })

  it('does not send an empty team name', async () => {
    reply({ teams: [] })
    await show()
    await click(byId('teams-create'))
    await click(byId('teams-create-confirm'))
    expect(post).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain(en.llcTeams.nameRequired)
  })

  it('shows the server refusal for a non-administrator and keeps the dialog open', async () => {
    reply({ teams: [] })
    post.mockRejectedValue(httpError(403))
    await show()
    await click(byId('teams-create'))
    const input = document.body.querySelector('input') as HTMLInputElement
    input.value = 'Growth'
    input.dispatchEvent(new Event('input'))
    await flushPromises()
    await click(byId('teams-create-confirm'))
    expect(byId('teams-create-error')?.textContent).toContain(en.llcTeams.forbidden)
    expect(byId('teams-create-confirm')).not.toBeNull()
  })

  it('says a duplicate team name is a duplicate', async () => {
    reply({ teams: [] })
    post.mockRejectedValue(httpError(409))
    await show()
    await click(byId('teams-create'))
    const input = document.body.querySelector('input') as HTMLInputElement
    input.value = 'Growth'
    input.dispatchEvent(new Event('input'))
    await flushPromises()
    await click(byId('teams-create-confirm'))
    expect(byId('teams-create-error')?.textContent).toContain(en.llcTeams.duplicateName)
  })

  it('deletes a team only after it is confirmed', async () => {
    reply(TEAMS)
    await show()
    await click(buttonNamed(en.llcTeams.deleteTeam))
    expect(del).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('Platform')
    await click(byId('teams-delete-confirm'))
    expect(del).toHaveBeenCalledWith('/api/user-management/teams/t1', { headers: { 'X-Organization-Id': 'coA' } })
  })

  it('ignores a teams response for a company no longer shown', async () => {
    let release!: (v: unknown) => void
    const late = new Promise((r) => { release = r })
    get.mockImplementation((url: string) => {
      if (url.includes('/coA/')) return url.endsWith('/teams') ? late : Promise.resolve([])
      return Promise.resolve(url.endsWith('/teams') ? { teams: [{ id: 'b1', name: 'B team', member_user_ids: [] }] } : [])
    })
    await show()
    route.params.companyId = 'coB'
    await flushPromises()
    release({ teams: [{ id: 'a1', name: 'A team', member_user_ids: [] }] })
    await flushPromises()
    expect(byId('teams-table')?.textContent).toContain('B team')
    expect(document.body.textContent).not.toContain('A team')
  })
})
