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
import componentsCss from '@/assets/css/components.css?raw'
import baseCardSource from '../../../../../libs/autobot-ui/src/components/BaseCard.vue?raw'
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

  it('is hidden in Full and shown in Minimal by the real `.only-min` rules of components.css', () => {
    const rules = [/^html:not\(\[data-ui="minimal"\]\) \.only-min\s*\{[^}]*\}/m, /^html\[data-ui="minimal"\] \.only-min\s*\{[^}]*\}/m]
      .map((re) => componentsCss.match(re)?.[0])
    expect(rules.every(Boolean)).toBe(true)
    // BaseCard's real scoped root rule (`.aui-card[data-v-x] { display: flex }`, 0,2,0) is what the
    // hide rule must outrank; its scope id is read from the mounted element below.
    const cardRule = baseCardSource.match(/^\.aui-card\s*\{[^}]*\}/m)?.[0]
    expect(cardRule).toContain('display: flex')
    const style = document.createElement('style')
    style.textContent = rules.join('\n')
    document.head.appendChild(style)
    const w = mount(AdvancedAreaNotice, {
      attachTo: document.body,
      global: { plugins: [i18n], stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } },
    })
    const el = w.get('[data-testid="advanced-area-notice"]').element
    // The root carries its own scope id and the parent's; one rule per id, so BaseCard's is included.
    const scopes = el.getAttributeNames().filter((n) => n.startsWith('data-v-'))
    expect(scopes.length).toBeGreaterThan(0)
    style.textContent += scopes.map((sc) => `\n${cardRule!.replace('.aui-card', `.aui-card[${sc}]`)}`).join('')
    document.documentElement.setAttribute('data-ui', 'full')
    expect(getComputedStyle(el).display).toBe('none')
    document.documentElement.setAttribute('data-ui', 'minimal')
    expect(getComputedStyle(el).display).not.toBe('none')
    w.unmount()
    style.remove()
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
