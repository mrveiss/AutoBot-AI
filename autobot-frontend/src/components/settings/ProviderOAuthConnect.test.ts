// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/** ProviderOAuthConnect (#19241): server-driven sign-in, no endpoints in the SPA. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const post = vi.fn()
const get = vi.fn()
const del = vi.fn()
vi.mock('@/utils/ApiClient', () => ({
  default: {
    post: (...a: unknown[]) => post(...a),
    get: (...a: unknown[]) => get(...a),
    delete: (...a: unknown[]) => del(...a),
  },
}))
const confirm = vi.fn()
vi.mock('@/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: (...a: unknown[]) => confirm(...a) }),
}))
vi.mock('@/config/ssot-config', () => ({
  getConfig: () => ({ frontendUrl: 'https://app.example.test' }),
}))

import ProviderOAuthConnect from './ProviderOAuthConnect.vue'
import { PROVIDER_OAUTH_CALLBACK_PATH } from '@/utils/providerOAuth'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const mountIt = (props: Record<string, unknown>) =>
  mount(ProviderOAuthConnect, {
    props: { providerName: 'openai', providerLabel: 'OpenAI', scope: 'user', ...props },
    global: { plugins: [i18n] },
  })

beforeEach(() => {
  post.mockReset()
  get.mockReset()
  del.mockReset()
  get.mockResolvedValue({ provider_name: 'openai', connected: false })
})

describe('ProviderOAuthConnect', () => {
  it('initiate posts provider/redirect_uri/scope and navigates to authorize_url', async () => {
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, assign })
    post.mockResolvedValue({ authorize_url: 'https://idp.example.test/authorize?x=1', state: 's' })
    const wrapper = mountIt({ flows: ['redirect'], configured: true })
    await flushPromises()
    await wrapper.get('[data-testid="provider-signin"]').trigger('click')
    await flushPromises()
    expect(post).toHaveBeenCalledWith('/api/llm-auth/oauth/initiate', {
      provider_name: 'openai',
      redirect_uri: `https://app.example.test${PROVIDER_OAUTH_CALLBACK_PATH}`,
      scope: 'user',
    })
    expect(assign).toHaveBeenCalledWith('https://idp.example.test/authorize?x=1')
    vi.unstubAllGlobals()
  })

  it('unconfigured provider shows setting names and no sign-in button', async () => {
    const wrapper = mountIt({
      configured: false,
      flows: [],
      missingSettings: ['AUTOBOT_LLM_OAUTH_OPENAI_CLIENT_ID'],
    })
    await flushPromises()
    const box = wrapper.get('[data-testid="provider-not-configured"]')
    expect(box.text()).toContain('AUTOBOT_LLM_OAUTH_OPENAI_CLIENT_ID')
    expect(wrapper.find('[data-testid="provider-signin"]').exists()).toBe(false)
  })

  it('a provider-rejected sign-in shows the needs-re-sign-in state and offers sign-in again', async () => {
    get.mockResolvedValue({ provider_name: 'openai', connected: false, needs_reauth: true, scope: 'user' })
    const wrapper = mountIt({ flows: ['redirect'], configured: true })
    await flushPromises()
    await wrapper.findAll('.auth-tab').at(-1)?.trigger('click')
    expect(wrapper.get('[data-testid="needs-reauth"]').text()).toContain(
      en.settings.providerAuth.needsReauth.replace('{provider}', 'OpenAI'),
    )
    expect(wrapper.find('[data-testid="provider-signin"]').exists()).toBe(true)
  })

  it('disconnect sends the scope and surfaces a provider-side revoke failure', async () => {
    get.mockResolvedValue({ provider_name: 'openai', connected: true, scope: 'user' })
    del.mockResolvedValue({ provider_revoked: false, provider_error: 'HTTP 500' })
    const wrapper = mountIt({ flows: ['redirect'], configured: true })
    await flushPromises()
    await wrapper.get('.btn-danger-sm').trigger('click')
    await flushPromises()
    expect(del).toHaveBeenCalledWith('/api/llm-auth/openai?scope=user')
    expect(wrapper.get('[data-testid="revoke-warning"]').text()).toContain('HTTP 500')
  })

  it('an org-less admin sees that only a superadmin can revoke the shared System sign-in', async () => {
    get.mockResolvedValue({ provider_name: 'openai', connected: true, scope: 'system', shared: true })
    const wrapper = mountIt({ scope: 'system', flows: ['redirect'], configured: true })
    await flushPromises()
    expect(wrapper.find('[data-testid="shared-superadmin-only"]').exists()).toBe(true)
    expect(wrapper.find('.btn-danger-sm').exists()).toBe(false)  // no plain disconnect: it would be refused
  })

  it('a superadmin is led to the confirmed shared revoke instead', async () => {
    get.mockResolvedValue({ provider_name: 'openai', connected: true, scope: 'system', shared: true })
    confirm.mockResolvedValue(true)
    del.mockResolvedValue({ provider_revoked: true })
    const wrapper = mountIt({ scope: 'system', flows: ['redirect'], configured: true, canRevokeShared: true })
    await flushPromises()
    await wrapper.get('[data-testid="shared-revoke-inline"]').trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(del).toHaveBeenCalledWith('/api/llm-auth/openai/shared')
  })
})
