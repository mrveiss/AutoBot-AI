// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/** Superadmin shared-token revoke (#19241, owner decision 2026-10-23): superadmin-only, confirmed first. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const del = vi.fn()
const get = vi.fn()
const confirm = vi.fn()
const role = { value: 'admin' }
vi.mock('@/utils/ApiClient', () => ({
  default: { delete: (...a: unknown[]) => del(...a), get: (...a: unknown[]) => get(...a) },
}))
vi.mock('@/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: (...a: unknown[]) => confirm(...a) }),
}))
vi.mock('@/stores/useUserStore', () => ({
  useUserStore: () => ({ currentUser: { role: role.value } }),
}))

import SharedTokenRevoke from './SharedTokenRevoke.vue'
import ProviderAccountsSection from './ProviderAccountsSection.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const PROVIDERS = [{ name: 'openai', label: 'OpenAI', flows: ['redirect'], configured: true, missing_settings: [] }]

// mockReset: true (vitest.config.ts, #3070) wipes implementations, so they are applied here.
beforeEach(() => {
  get.mockResolvedValue(PROVIDERS)
  del.mockResolvedValue({ provider_revoked: true })
  role.value = 'admin'
})

describe('SharedTokenRevoke', () => {
  it('does nothing until the superadmin confirms', async () => {
    confirm.mockResolvedValue(false)
    const wrapper = mount(SharedTokenRevoke, { props: { providers: PROVIDERS }, global: { plugins: [i18n] } })
    await wrapper.get('[data-testid="shared-revoke-openai"]').trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(del).not.toHaveBeenCalled()
  })

  it('revokes the shared token after confirmation', async () => {
    confirm.mockResolvedValue(true)
    const wrapper = mount(SharedTokenRevoke, { props: { providers: PROVIDERS }, global: { plugins: [i18n] } })
    await wrapper.get('[data-testid="shared-revoke-openai"]').trigger('click')
    await flushPromises()
    expect(del).toHaveBeenCalledWith('/api/llm-auth/openai/shared')
    expect(wrapper.text()).toContain(en.settings.providerAuth.shared.done.replace('{provider}', 'OpenAI'))
  })
})

describe('ProviderAccountsSection shared revoke visibility', () => {
  const mountSection = () =>
    mount(ProviderAccountsSection, {
      props: { isAdmin: true },
      global: { plugins: [i18n], stubs: { ProviderOAuthConnect: true } },
    })

  it('is hidden from an org admin', async () => {
    const wrapper = mountSection()
    await flushPromises()
    expect(wrapper.find('[data-testid="shared-token-revoke"]').exists()).toBe(false)
  })

  it('is shown to a superadmin', async () => {
    role.value = 'superadmin'
    const wrapper = mountSection()
    await flushPromises()
    expect(wrapper.find('[data-testid="shared-token-revoke"]').exists()).toBe(true)
  })
})
