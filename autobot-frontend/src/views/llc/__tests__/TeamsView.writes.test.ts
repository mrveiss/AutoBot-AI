// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #14106: the Teams screen creates and deletes a team and adds and removes a member through the
// company-scoped routes (company in the path, no organisation header). A refusal is shown, a delete
// asks first, and every write re-reads the teams.

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { reactive } from 'vue'
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
  { user_id: 'u4', display_name: 'Left Person', role: 'member', is_active: false },
]
const TEAMS = { teams: [{ id: 't1', name: 'Platform', member_user_ids: ['u1'] }] }
const httpError = (status: number) => Object.assign(new Error(`http ${status}`), { status })

let wrapper: VueWrapper
const byId = (id: string) => document.body.querySelector<HTMLElement>(`[data-testid="${id}"]`)
const click = async (el: Element | null) => { (el as HTMLElement).click(); await flushPromises() }
const buttonNamed = (text: string) => [...document.body.querySelectorAll('button')].find((b) => b.textContent?.trim() === text) ?? null
const teamsReads = () => get.mock.calls.filter((c) => c[0] === '/api/llc/companies/coA/teams').length

async function show(): Promise<void> {
  wrapper = mount(TeamsView, { attachTo: document.body, global: { plugins: [i18n] } })
  await flushPromises()
}
async function typeName(value: string): Promise<void> {
  const input = document.body.querySelector<HTMLInputElement>('input')
  if (!input) throw new Error('no name input')
  input.value = value
  input.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
}
async function pickCandidate(userId: string): Promise<void> {
  // The select is a kit component; its value is the view's own state.
  const vm = wrapper.vm as unknown as { candidateId: string }
  vm.candidateId = userId
  await flushPromises()
}

describe('TeamsView writes (#14106)', () => {
  beforeEach(() => {
    for (const m of [get, post, del]) m.mockReset()
    route.params.companyId = 'coA'
    get.mockImplementation((url: string) => Promise.resolve(url.endsWith('/teams') ? TEAMS : { members: MEMBERS, viewer_can_manage: true, viewer_role: 'owner', viewer_grantable_roles: [] }))
    post.mockResolvedValue({})
    del.mockResolvedValue({})
  })
  afterEach(() => { wrapper?.unmount(); document.body.innerHTML = '' })

  it('creates a team at the company path with no header, then re-reads', async () => {
    await show()
    await click(byId('teams-create'))
    await typeName('  Ops  ')
    await click(byId('teams-create-confirm'))
    expect(post).toHaveBeenCalledTimes(1)
    expect(post.mock.calls[0]).toEqual(['/api/llc/companies/coA/teams', { name: 'Ops' }])
    expect(teamsReads()).toBe(2)
    expect(byId('teams-create-confirm')).toBeNull()
  })

  it('does not send an empty team name', async () => {
    await show()
    await click(byId('teams-create'))
    await click(byId('teams-create-confirm'))
    expect(post).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain(en.llcTeams.nameRequired)
  })

  it('says only company owners and admins can when create is refused with 403, and keeps the form', async () => {
    post.mockRejectedValue(httpError(403))
    await show()
    await click(byId('teams-create'))
    await typeName('Ops')
    await click(byId('teams-create-confirm'))
    expect(byId('teams-create-error')?.textContent).toContain('Only company owners and admins can')
    expect(byId('teams-create-confirm')).not.toBeNull()
  })

  it('says the name is taken on 409 and a plain failure otherwise', async () => {
    post.mockRejectedValueOnce(httpError(409)).mockRejectedValueOnce(httpError(500))
    await show()
    await click(byId('teams-create'))
    await typeName('Platform')
    await click(byId('teams-create-confirm'))
    expect(byId('teams-create-error')?.textContent).toContain(en.llcTeams.duplicateName)
    await click(byId('teams-create-confirm'))
    expect(byId('teams-create-error')?.textContent).toContain(en.llcTeams.createError)
  })

  it('asks before deleting, and deletes nothing on cancel', async () => {
    await show()
    await click(byId('team-delete'))
    expect(document.body.textContent).toContain('Delete the team "Platform"')
    expect(del).not.toHaveBeenCalled()
    await click(buttonNamed(en.common.cancel))
    expect(del).not.toHaveBeenCalled()
  })

  it('deletes the team at the company path once confirmed, then re-reads', async () => {
    await show()
    await click(byId('team-delete'))
    await click(byId('teams-delete-confirm'))
    expect(del).toHaveBeenCalledWith('/api/llc/companies/coA/teams/t1')
    expect(teamsReads()).toBe(2)
    expect(byId('teams-delete-confirm')).toBeNull()
  })

  it('reports a refused delete (403) and keeps the team on screen', async () => {
    del.mockRejectedValue(httpError(403))
    await show()
    await click(byId('team-delete'))
    await click(byId('teams-delete-confirm'))
    expect(byId('teams-delete-error')?.textContent).toContain(en.llcTeams.forbidden)
    expect(byId('teams-table')?.textContent).toContain('Platform')
  })

  it('adds a person not yet on the team at the company path', async () => {
    await show()
    await click(buttonNamed(en.llcTeams.viewMembers))
    expect(byId('team-add')?.textContent).not.toContain('Left Person')
    await pickCandidate('u2')
    await click(byId('team-add-member'))
    expect(post).toHaveBeenCalledWith('/api/llc/companies/coA/teams/t1/members/u2')
  })

  it('reports a refused add (403)', async () => {
    post.mockRejectedValue(httpError(403))
    await show()
    await click(buttonNamed(en.llcTeams.viewMembers))
    await pickCandidate('u2')
    await click(byId('team-add-member'))
    expect(byId('teams-error')?.textContent).toContain(en.llcTeams.forbidden)
  })

  it('removes a member at the company path', async () => {
    await show()
    await click(buttonNamed(en.llcTeams.viewMembers))
    await click(byId('team-remove-member'))
    expect(del).toHaveBeenCalledWith('/api/llc/companies/coA/teams/t1/members/u1')
  })

  it('reports a refused remove (403)', async () => {
    del.mockRejectedValue(httpError(403))
    await show()
    await click(buttonNamed(en.llcTeams.viewMembers))
    await click(byId('team-remove-member'))
    expect(byId('teams-error')?.textContent).toContain(en.llcTeams.forbidden)
  })

  it('shows no write control while the teams cannot be read', async () => {
    get.mockImplementation((url: string) => (url.endsWith('/teams') ? Promise.reject(httpError(403)) : Promise.resolve({ members: MEMBERS, viewer_can_manage: true, viewer_role: 'owner', viewer_grantable_roles: [] })))
    await show()
    expect(byId('teams-unavailable')).not.toBeNull()
    expect(byId('teams-create')).toBeNull()
    expect(byId('team-delete')).toBeNull()
  })
})
