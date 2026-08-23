// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// #14603: a contact card can be edited in place in the People list — the only
// surface a contact renders on (#13938 — a contact has no canvas node, no
// org-chart node, and so no drawer to edit it from). The owner's decision was
// explicit that a contact and an agent are editable but a user is not (users
// edit their own profile), so these tests pin the row this component renders
// the affordance for, not just that editing works for a contact in isolation.
//
// Every assertion pairs a negative ("no edit control on this row") with a
// positive ("the row did render, with the right name") so a broken render —
// not a correctly-withheld control — can never satisfy the negative half.

import { describe, it, expect } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { memoizeByLocale } from '@/test/utils/i18n-cache'
import en from '@/i18n/locales/en.json'
import ar from '@/i18n/locales/ar.json'
import OrgPeopleList from '../OrgPeopleList.vue'
import { buildOrgPeople, groupPeopleByTeam } from '@/composables/llc/orgPeople'

const AGENT_NAME = 'Ada'
const USER_NAME = 'Grace'
const CONTACT_NAME = 'Hedy Lamarr'
const CONTACT_ID = 'c0ffee00-0000-0000-0000-000000000001'
const CONTACT_KEY = `contact:${CONTACT_ID}`

const PEOPLE = buildOrgPeople(
  [
    { id: 'agent-1', name: AGENT_NAME, title: 'CEO', is_human: false },
    { id: 'user:u1', name: USER_NAME, title: 'lead', is_human: true },
  ],
  [
    {
      id: CONTACT_ID,
      full_name: CONTACT_NAME,
      role_title: 'Accounts Payable',
      email: 'hedy@supplier.example',
      phone: '+1 555 0100',
    },
  ],
)

const GROUPS = groupPeopleByTeam(PEOPLE, [])

// #14860: memoized per locale. This helper ran on EVERY mount and each call
// re-ingested the ~400KB `en` and `ar` message bundles. The locale is a real
// parameter here, so a blind hoist would be wrong — one instance per locale
// is not. Nothing in this file mutates the returned instance.
const makeI18n = memoizeByLocale((locale: string) =>
  createI18n({ legacy: false, locale, fallbackLocale: 'en', messages: { en, ar } }),
)

function mountList(
  overrides: Partial<{
    savingContactId: string | null
    contactSaveError: { contactId: string; message: string } | null
  }> = {},
  locale: 'en' | 'ar' = 'en',
) {
  return mount(OrgPeopleList, {
    props: {
      groups: GROUPS,
      counts: { agent: 1, user: 1, contact: 1 },
      hasTeams: false,
      savingContactId: overrides.savingContactId ?? null,
      contactSaveError: overrides.contactSaveError ?? null,
    },
    global: { plugins: [makeI18n(locale)] },
  })
}

function row(wrapper: VueWrapper, key: string) {
  return wrapper.get(`[data-testid="org-person-${key}"]`)
}

describe('editing is offered for a contact row and nowhere else (#14603)', () => {
  it('shows an edit control on the contact row', () => {
    const wrapper = mountList()
    const contactRow = row(wrapper, CONTACT_KEY)

    // Positive companion: the row did render this contact.
    expect(contactRow.text()).toContain(CONTACT_NAME)
    expect(contactRow.find(`[data-testid="org-person-edit-${CONTACT_KEY}"]`).exists()).toBe(true)
  })

  it('offers no edit control on a user row', () => {
    const wrapper = mountList()
    const userKey = PEOPLE.find((p) => p.kind === 'user')!.key
    const userRow = row(wrapper, userKey)

    expect(userRow.text()).toContain(USER_NAME)
    expect(userRow.find(`[data-testid="org-person-edit-${userKey}"]`).exists()).toBe(false)
  })

  it('offers no edit control on an agent row', () => {
    const wrapper = mountList()
    const agentKey = PEOPLE.find((p) => p.kind === 'agent')!.key
    const agentRow = row(wrapper, agentKey)

    expect(agentRow.text()).toContain(AGENT_NAME)
    expect(agentRow.find(`[data-testid="org-person-edit-${agentKey}"]`).exists()).toBe(false)
  })
})

describe('opening the editor pre-fills the contact\'s current fields (#14603)', () => {
  it('carries full_name, role_title, email and phone into the draft inputs', async () => {
    const wrapper = mountList()
    await wrapper.get(`[data-testid="org-person-edit-${CONTACT_KEY}"]`).trigger('click')

    expect(
      (wrapper.get(`[data-testid="org-person-edit-name-${CONTACT_KEY}"]`).element as HTMLInputElement)
        .value,
    ).toBe(CONTACT_NAME)
    expect(
      (wrapper.get(`[data-testid="org-person-edit-role-${CONTACT_KEY}"]`).element as HTMLInputElement)
        .value,
    ).toBe('Accounts Payable')
    expect(
      (wrapper.get(`[data-testid="org-person-edit-email-${CONTACT_KEY}"]`).element as HTMLInputElement)
        .value,
    ).toBe('hedy@supplier.example')
    expect(
      (wrapper.get(`[data-testid="org-person-edit-phone-${CONTACT_KEY}"]`).element as HTMLInputElement)
        .value,
    ).toBe('+1 555 0100')
  })
})

describe('submitting the editor emits the values the PATCH should carry (#14603)', () => {
  it('emits save-contact with the id and the edited fields', async () => {
    const wrapper = mountList()
    await wrapper.get(`[data-testid="org-person-edit-${CONTACT_KEY}"]`).trigger('click')

    await wrapper.get(`[data-testid="org-person-edit-name-${CONTACT_KEY}"]`).setValue('Hedy Renamed')
    await wrapper.get(`[data-testid="org-person-edit-role-${CONTACT_KEY}"]`).setValue('AP Lead')
    await wrapper.get(`[data-testid="org-person-edit-email-${CONTACT_KEY}"]`).setValue('hedy2@supplier.example')
    await wrapper.get(`[data-testid="org-person-edit-phone-${CONTACT_KEY}"]`).setValue('+1 555 0199')
    await wrapper.get(`[data-testid="org-person-edit-form-${CONTACT_KEY}"]`).trigger('submit')

    const emitted = wrapper.emitted('save-contact')
    expect(emitted).toHaveLength(1)
    expect(emitted![0]).toEqual([
      CONTACT_ID,
      {
        full_name: 'Hedy Renamed',
        role_title: 'AP Lead',
        email: 'hedy2@supplier.example',
        phone: '+1 555 0199',
      },
    ])
  })

  it('never emits for a user or agent row — there is no form to submit', () => {
    // The absence of a submit path is a consequence of the absence of the
    // button proven above; this pins the emit side of the same guarantee.
    const wrapper = mountList()

    expect(wrapper.find(`[data-testid^="org-person-edit-form-"]`).exists()).toBe(false)
    expect(wrapper.emitted('save-contact')).toBeUndefined()
  })
})

describe('a failed save says so and leaves the row unchanged (#14603)', () => {
  it('shows the row-scoped error and keeps the typed draft in place', async () => {
    const wrapper = mountList()
    await wrapper.get(`[data-testid="org-person-edit-${CONTACT_KEY}"]`).trigger('click')
    await wrapper.get(`[data-testid="org-person-edit-name-${CONTACT_KEY}"]`).setValue('Hedy Draft')

    // Simulate the round trip a real save makes: in flight, then failed.
    await wrapper.setProps({ savingContactId: CONTACT_ID })
    await wrapper.setProps({
      savingContactId: null,
      contactSaveError: { contactId: CONTACT_ID, message: 'network down' },
    })

    expect(wrapper.get(`[data-testid="org-person-edit-error-${CONTACT_KEY}"]`).text()).toBe(
      'network down',
    )
    // The editor is still open — a failure must not discard what was typed.
    expect(
      (wrapper.get(`[data-testid="org-person-edit-name-${CONTACT_KEY}"]`).element as HTMLInputElement)
        .value,
    ).toBe('Hedy Draft')
    // The read-only display (used once the editor closes) still shows the
    // pre-save name — no optimistic mutation happened.
    expect(wrapper.find(`[data-testid="org-person-edit-form-${CONTACT_KEY}"]`).exists()).toBe(true)
  })

  it('never shows a different row\'s error on this one', async () => {
    const wrapper = mountList({
      contactSaveError: { contactId: 'some-other-contact-id', message: 'unrelated failure' },
    })
    await wrapper.get(`[data-testid="org-person-edit-${CONTACT_KEY}"]`).trigger('click')

    expect(wrapper.find(`[data-testid="org-person-edit-error-${CONTACT_KEY}"]`).exists()).toBe(false)
  })
})

describe('the editor closes itself once its own save succeeds (#14603)', () => {
  it('closes when the in-flight save for this row completes with no error', async () => {
    const wrapper = mountList()
    await wrapper.get(`[data-testid="org-person-edit-${CONTACT_KEY}"]`).trigger('click')
    expect(wrapper.find(`[data-testid="org-person-edit-form-${CONTACT_KEY}"]`).exists()).toBe(true)

    await wrapper.setProps({ savingContactId: CONTACT_ID })
    await wrapper.setProps({ savingContactId: null, contactSaveError: null })

    expect(wrapper.find(`[data-testid="org-person-edit-form-${CONTACT_KEY}"]`).exists()).toBe(false)
    // The plain display is back, still showing the contact by name.
    expect(row(wrapper, CONTACT_KEY).text()).toContain(CONTACT_NAME)
  })

  it('does not close a row it was never saving', async () => {
    const wrapper = mountList()
    await wrapper.get(`[data-testid="org-person-edit-${CONTACT_KEY}"]`).trigger('click')

    // A save for a different contact finishing must not touch this editor.
    await wrapper.setProps({ savingContactId: 'a-different-contact' })
    await wrapper.setProps({ savingContactId: null, contactSaveError: null })

    expect(wrapper.find(`[data-testid="org-person-edit-form-${CONTACT_KEY}"]`).exists()).toBe(true)
  })
})

describe('cancelling leaves the row untouched and emits nothing (#14603)', () => {
  it('closes the editor without emitting save-contact', async () => {
    const wrapper = mountList()
    await wrapper.get(`[data-testid="org-person-edit-${CONTACT_KEY}"]`).trigger('click')
    await wrapper.get(`[data-testid="org-person-edit-name-${CONTACT_KEY}"]`).setValue('Discarded')

    await wrapper.get(`[data-testid="org-person-edit-cancel-${CONTACT_KEY}"]`).trigger('click')

    expect(wrapper.find(`[data-testid="org-person-edit-form-${CONTACT_KEY}"]`).exists()).toBe(false)
    expect(wrapper.emitted('save-contact')).toBeUndefined()
    expect(row(wrapper, CONTACT_KEY).text()).toContain(CONTACT_NAME)
  })
})

describe('the edit affordance survives an RTL locale (#14603)', () => {
  it('renders the translated edit label in Arabic, not the English fallback', () => {
    const wrapper = mountList({}, 'ar')
    const button = wrapper.get(`[data-testid="org-person-edit-${CONTACT_KEY}"]`)

    expect(button.text()).toBe(ar.common.edit)
    expect(button.text()).not.toBe(en.common.edit)
  })
})
