// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// #17850: the duplicated-credentials section is part of the Secrets page, reached at /secrets?view=duplicates.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const state = vi.hoisted(() => ({ query: {} as Record<string, string>, isAdmin: true }))

vi.mock('vue-router', () => ({ useRoute: () => ({ query: state.query }) }))
vi.mock('@/stores/useUserStore', () => ({ useUserStore: () => state }))

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

import SecretsView from '../SecretsView.vue'

function mountView() {
  return mount(SecretsView, {
    global: {
      plugins: [i18n],
      stubs: {
        Icon: true,
        RouterLink: { props: ['to'], template: '<a :data-to="JSON.stringify(to)"><slot /></a>' },
        RouterView: { template: '<div data-testid="manager" />' },
        DuplicateSecrets: { template: '<div data-testid="duplicates" />' },
      },
    },
  })
}

describe('SecretsView.vue duplicates section', () => {
  beforeEach(() => {
    state.query = {}
    state.isAdmin = true
  })

  it('shows the manager by default and offers the duplicates section as a tab for admins', () => {
    const wrapper = mountView()
    expect(wrapper.find('[data-testid="manager"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="duplicates"]').exists()).toBe(false)
    expect(wrapper.find('a[data-to*="duplicates"]').exists()).toBe(true)
  })

  it('shows the duplicates section at /secrets?view=duplicates', () => {
    state.query = { view: 'duplicates' }
    const wrapper = mountView()
    expect(wrapper.find('[data-testid="duplicates"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="manager"]').exists()).toBe(false)
  })

  it('never shows the duplicates section to a non-admin, even with the query', () => {
    state.query = { view: 'duplicates' }
    state.isAdmin = false
    const wrapper = mountView()
    expect(wrapper.find('[data-testid="duplicates"]').exists()).toBe(false)
    expect(wrapper.find('a[data-to*="duplicates"]').exists()).toBe(false)
  })
})
