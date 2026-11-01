// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #18245: the Teams screen says loading, empty, couldn't-read and not-available apart, names members from
// the company's member list, and nothing on it writes (read-only until the company-scoped write routes land, #14106).

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { reactive } from 'vue'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
const route = reactive({ params: { companyId: 'coA' } })

vi.mock('vue-router', () => ({ useRoute: () => route }))
vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get }) }))
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

function reply(teams: unknown, members: unknown = MEMBERS) {
  get.mockImplementation((url: string) => {
    const out = url.endsWith('/teams') ? teams : members
    return out instanceof Error ? Promise.reject(out) : Promise.resolve(out)
  })
}
const httpError = (status: number) => Object.assign(new Error(`http ${status}`), { status })

let wrapper: VueWrapper
async function show(): Promise<VueWrapper> {
  wrapper = mount(TeamsView, { attachTo: document.body, global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}
const byId = (id: string) => document.body.querySelector<HTMLElement>(`[data-testid="${id}"]`)
const click = async (el: Element | null) => { (el as HTMLElement).click(); await flushPromises() }
const buttonNamed = (text: string) => [...document.body.querySelectorAll('button')].find((b) => b.textContent?.trim() === text) ?? null

describe('TeamsView (#18245)', () => {
  beforeEach(() => {
    get.mockReset()
    route.params.companyId = 'coA'
  })
  afterEach(() => wrapper?.unmount())

  it('shows an honest loading state until the first answer', async () => {
    get.mockReturnValue(new Promise(() => {}))
    wrapper = mount(TeamsView, { attachTo: document.body, global: { plugins: [i18n] } })
    await flushPromises()
    expect(byId('teams-loading')?.textContent).toContain(en.llcTeams.loading)
    expect(byId('teams-empty')).toBeNull()
  })

  it('offers no create, delete, add or remove control', async () => {
    reply(TEAMS)
    await show()
    await click(buttonNamed(en.llcTeams.viewMembers))
    const labels = [...document.body.querySelectorAll('button')].map((b) => b.textContent?.trim())
    expect(labels).toEqual([en.llcTeams.viewMembers, en.llcTeams.viewMembers])
    expect(document.body.querySelector('input, select, [role="dialog"]')).toBeNull()
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
  })

  it('says it could not read the teams, offers a retry, and never says "no teams"', async () => {
    reply(httpError(500))
    await show()
    expect(byId('teams-failed')?.textContent).toContain(en.llcTeams.loadError)
    expect(byId('teams-empty')).toBeNull()
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
    await click(buttonNamed(en.llcTeams.viewMembers))
    const text = byId('team-members')?.textContent ?? ''
    expect(text.match(/Alex Smith/g)).toHaveLength(2)
    expect(text).toContain('member')
    expect(text).toContain('guest')
  })

  it('shows members without invented names when the member list cannot be read', async () => {
    reply(TEAMS, httpError(500))
    await show()
    await click(buttonNamed(en.llcTeams.viewMembers))
    expect(byId('teams-names-error')?.textContent).toContain(en.llcTeams.namesError)
    expect(byId('team-members')?.textContent).toContain(en.llcTeams.unknownMember)
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
