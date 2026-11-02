// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * TranscriberLayout offers its settings panel to admins only (#15758), and an
 * already-open panel closes when the session stops being admin (#16335).
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { reactive } from 'vue'
import TranscriberLayout from '../transcriber/TranscriberLayout.vue'

const user = reactive({ isAdmin: true })

vi.mock('@/stores/useUserStore', () => ({ useUserStore: () => user }))

// Not the English text, so a hardcoded English string cannot pass for a translated one.
const layout = { settingsButton: 'open-x', hideSettingsButton: 'hide-x', settingsHeading: 'heading-x' }
const i18n = createI18n({ legacy: false, locale: 'en', messages: { en: { transcriber: { layout } } }, missingWarn: false, fallbackWarn: false })

function mountLayout() {
  return mount(TranscriberLayout, {
    global: {
      plugins: [i18n],
      stubs: { RouterView: true, AsrProviderSelector: { template: '<div data-test="asr" />' } },
    },
  })
}

describe('TranscriberLayout settings', () => {
  it('labels come from the locale file', async () => {
    user.isAdmin = true
    const w = mountLayout()
    expect(w.find('button').text()).toBe(layout.settingsButton)
    await w.find('button').trigger('click')
    expect(w.find('button').text()).toBe(layout.hideSettingsButton)
    expect(w.find('h2').text()).toBe(layout.settingsHeading)
  })

  it('closes an open panel when the session is demoted', async () => {
    user.isAdmin = true
    const w = mountLayout()
    await w.find('button').trigger('click')
    expect(w.find('[data-test="asr"]').exists()).toBe(true)
    user.isAdmin = false
    await w.vm.$nextTick()
    expect(w.find('[data-test="asr"]').exists()).toBe(false)
  })

  it('does not reopen by itself when the role comes back', async () => {
    user.isAdmin = true
    const w = mountLayout()
    await w.find('button').trigger('click')
    user.isAdmin = false
    await w.vm.$nextTick()
    user.isAdmin = true
    await w.vm.$nextTick()
    expect(w.find('[data-test="asr"]').exists()).toBe(false)
    expect(w.find('button').text()).toBe(layout.settingsButton)
  })
})
