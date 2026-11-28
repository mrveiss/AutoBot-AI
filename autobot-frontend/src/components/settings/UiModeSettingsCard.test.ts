// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * UiModeSettingsCard (#18240): the two mode cards are pressed-state buttons,
 * "Start in" is a radiogroup, and both write the shared useUiMode state.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import UiModeSettingsCard from './UiModeSettingsCard.vue'
import { useUiMode } from '@/composables/useUiMode'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const mountCard = () => mount(UiModeSettingsCard, { attachTo: document.body, global: { plugins: [i18n] } })

beforeEach(() => {
  document.body.innerHTML = ''
  localStorage.clear()
  const ui = useUiMode()
  ui.setMode('full')
  ui.setStart('last')
})

describe('UiModeSettingsCard', () => {
  it('shows Full pressed and Last used checked by default', () => {
    const wrapper = mountCard()
    expect(wrapper.get('[data-testid="ui-mode-full"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('[data-testid="ui-mode-minimal"]').attributes('aria-pressed')).toBe('false')
    expect(wrapper.get('[data-testid="ui-start-last"]').attributes('aria-checked')).toBe('true')
    expect(wrapper.get('[role="radiogroup"]').exists()).toBe(true)
  })

  it('picking Minimal switches the interface mode', async () => {
    const wrapper = mountCard()
    await wrapper.get('[data-testid="ui-mode-minimal"]').trigger('click')
    expect(useUiMode().uiMode.value).toBe('minimal')
    expect(document.documentElement.getAttribute('data-ui')).toBe('minimal')
    expect(wrapper.get('[data-testid="ui-mode-minimal"]').attributes('aria-pressed')).toBe('true')
  })

  it('picking a start option stores it; arrow keys move the radio', async () => {
    const wrapper = mountCard()
    await wrapper.get('[data-testid="ui-start-minimal"]').trigger('click')
    expect(useUiMode().uiStart.value).toBe('minimal')

    await wrapper.get('[role="radiogroup"]').trigger('keydown', { key: 'ArrowRight' })
    expect(useUiMode().uiStart.value).toBe('full')
    expect(wrapper.get('[data-testid="ui-start-full"]').attributes('aria-checked')).toBe('true')
  })
})
