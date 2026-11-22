// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AdvancedAreaNotice (#18244): carries `only-min` so the shared CSS shows it only in
 * Minimal mode; "Show all features" switches to Full mode through useUiMode.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import AdvancedAreaNotice from '../AdvancedAreaNotice.vue'
import { useUiMode } from '@/composables/useUiMode'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const mountNotice = () =>
  mount(AdvancedAreaNotice, {
    global: { plugins: [i18n], stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } },
  })

beforeEach(() => {
  localStorage.clear()
  useUiMode().setMode('minimal')
})

describe('AdvancedAreaNotice', () => {
  it('is an only-min region named by its heading', () => {
    const w = mountNotice()
    const root = w.get('[data-testid="advanced-area-notice"]')
    expect(root.classes()).toContain('only-min')
    const heading = w.get('h2')
    expect(heading.text()).toBe(en.ui.advancedArea.title)
    expect(root.attributes('aria-labelledby')).toBe(heading.attributes('id'))
  })

  it('"Show all features" switches the UI to Full mode', async () => {
    const w = mountNotice()
    await w.get('[data-testid="advanced-area-show-all"]').trigger('click')
    expect(useUiMode().uiMode.value).toBe('full')
    expect(document.documentElement.getAttribute('data-ui')).toBe('full')
  })

  it('offers a way out to Home', () => {
    const link = mountNotice().findAll('a').find((a) => a.text() === en.ui.advancedArea.goHome)
    expect(link?.attributes('href')).toBe('/')
  })
})
