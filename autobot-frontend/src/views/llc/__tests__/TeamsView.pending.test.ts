// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #20816: teams render when their own read answers while the members read is pending (names shown as a
// skeleton, never "Unknown member"); the role column is translated through the shared roleLabel.

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { reactive } from 'vue'
import en from '@/i18n/locales/en.json'
import { roleLabelFor } from '@/composables/llc/roleLabel'

const get = vi.fn()
const route = reactive({ params: { companyId: 'coA' } })

vi.mock('vue-router', () => ({ useRoute: () => route }))
vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get, post: vi.fn(), delete: vi.fn() }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import TeamsView from '../TeamsView.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
const TEAMS = { teams: [{ id: 't1', name: 'Platform', member_user_ids: ['u1'] }] }
const MEMBERS = [{ user_id: 'u1', display_name: 'Jane Doe', role: 'owner', is_active: true }]

let wrapper: VueWrapper
const byId = (id: string) => document.body.querySelector<HTMLElement>(`[data-testid="${id}"]`)
const click = async (el: Element | null) => { (el as HTMLElement).click(); await flushPromises() }
const viewMembersButton = () => [...document.body.querySelectorAll('button')].find((b) => b.textContent?.trim() === en.llcTeams.viewMembers) ?? null

async function show(members: Promise<unknown>) {
  get.mockImplementation((url: string) => (url.endsWith('/teams') ? Promise.resolve(TEAMS) : members))
  wrapper = mount(TeamsView, { attachTo: document.body, global: { plugins: [i18n] } })
  await flushPromises()
}

describe('TeamsView pending members and role labels (#20816)', () => {
  beforeEach(() => { get.mockReset() })
  afterEach(() => wrapper?.unmount())

  it('renders the teams while the members read never resolves, with names pending', async () => {
    await show(new Promise(() => {}))
    expect(byId('teams-table')?.textContent).toContain('Platform')
    expect(byId('teams-loading')).toBeNull()
    await click(viewMembersButton())
    expect(byId('team-member-name-pending')).not.toBeNull()
    expect(byId('team-members')?.textContent).not.toContain(en.llcTeams.unknownMember)
  })

  it('shows the translated role once members arrive', async () => {
    await show(Promise.resolve(MEMBERS))
    await click(viewMembersButton())
    const table = byId('team-members')?.textContent ?? ''
    expect(table).toContain('Jane Doe')
    expect(table).toContain(en.llcMembers.role.owner)
    expect(byId('team-member-name-pending')).toBeNull()
  })

  it('keeps an unknown role code as the code, not as a key path', () => {
    const t = (k: string) => (k === 'llcMembers.role.owner' ? 'Owner' : k)
    expect(roleLabelFor(t, 'owner')).toBe('Owner')
    expect(roleLabelFor(t, 'custom')).toBe('custom')
  })
})
