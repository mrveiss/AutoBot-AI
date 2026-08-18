// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #13956: the badge is the whole point of showing an inactive person rather
// than hiding them. `isInactive` being correct is not enough — if the template
// stops binding it, the person renders indistinguishably from an active one
// and nothing fails.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import OrgPeopleList from '../OrgPeopleList.vue'
import { buildOrgPeople, groupPeopleByTeam } from '@/composables/llc/orgPeople'

const PEOPLE = buildOrgPeople(
  [
    { id: 'user:a', name: 'Ada', title: 'lead', is_human: true, is_active: true },
    { id: 'user:g', name: 'Grace', title: 'member', is_human: true, is_active: false },
  ],
  [],
)

function mountList() {
  const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
  return mount(OrgPeopleList, {
    props: {
      groups: groupPeopleByTeam(PEOPLE, []),
      counts: { agent: 0, user: 2, contact: 0 },
      hasTeams: false,
    },
    global: { plugins: [i18n] },
  })
}

describe('inactive badge on the people list (#13956)', () => {
  it('marks the inactive person', () => {
    expect(mountList().find('[data-testid="org-person-inactive-user:g"]').exists()).toBe(true)
  })

  it('does not mark the active person', () => {
    const w = mountList()
    // Positive companion: both people rendered, so the absence below is the
    // binding discriminating rather than the list failing to render.
    expect(w.text()).toContain('Ada')
    expect(w.find('[data-testid="org-person-inactive-user:a"]').exists()).toBe(false)
  })

  it('renders the translated label, not a bare key', () => {
    const badge = mountList().find('[data-testid="org-person-inactive-user:g"]')
    expect(badge.text()).toBe(en.llc.orgPeople.inactive)
    expect(badge.text()).not.toContain('llc.orgPeople')
  })
})
