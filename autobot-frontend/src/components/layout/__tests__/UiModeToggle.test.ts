// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * UiModeToggle — the header's Minimal / Full switch (#18240): a toggle button
 * (aria-pressed), focus stays on it, the change is announced in the kit's one
 * live region, and the mode lands on <html data-ui>.
 */
import { describe, it, expect, beforeAll, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const nextFrame = () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))

async function mountToggle() {
  vi.resetModules()
  const { default: UiModeToggle } = await import('../UiModeToggle.vue')
  return mount(UiModeToggle, { attachTo: document.body, global: { plugins: [i18n] } })
}


/**
 * Each test resets modules and re-imports a fresh instance. The first import also
 * pays the cold transform of the whole import graph, which under load outran the
 * default 10 s test timeout (pre-push, #18254). Warm the transform once here, with
 * its own budget, so every test measures only its own work.
 */
const COLD_IMPORT_MS = 60_000
beforeAll(async () => {
  await import('../UiModeToggle.vue')
}, COLD_IMPORT_MS)

beforeEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-ui')
  document.body.innerHTML = ''
})

describe('UiModeToggle', () => {
  it('starts unpressed in Full mode and describes itself with a tooltip', async () => {
    const wrapper = await mountToggle()
    const button = wrapper.get('[data-testid="ui-mode-toggle"]')
    expect(button.attributes('aria-pressed')).toBe('false')
    const tipId = button.attributes('aria-describedby')!
    expect(document.getElementById(tipId)?.textContent).toContain(en.nav.uiMode.tip)
  })

  it('has an accessible name even though the visible label is hidden below xl', async () => {
    const wrapper = await mountToggle()
    const button = wrapper.get('[data-testid="ui-mode-toggle"]')
    expect(wrapper.get('span.hidden').classes()).toContain('xl:inline')
    expect(button.attributes('aria-label')).toBe(en.nav.uiMode.label)
  })

  it('pressing it enters Minimal: aria-pressed, data-ui, and an announcement', async () => {
    const wrapper = await mountToggle()
    const button = wrapper.get('[data-testid="ui-mode-toggle"]')
    ;(button.element as HTMLButtonElement).focus()
    await button.trigger('click')
    await nextFrame()

    expect(button.attributes('aria-pressed')).toBe('true')
    expect(document.documentElement.getAttribute('data-ui')).toBe('minimal')
    expect(document.getElementById('a11y-live-region')?.textContent).toBe(en.nav.uiMode.announceMinimal)
    expect(document.activeElement).toBe(button.element)
  })

  it('pressing it again returns to Full and announces that', async () => {
    const wrapper = await mountToggle()
    const button = wrapper.get('[data-testid="ui-mode-toggle"]')
    await button.trigger('click')
    await button.trigger('click')
    await nextFrame()

    expect(button.attributes('aria-pressed')).toBe('false')
    expect(document.documentElement.getAttribute('data-ui')).toBe('full')
    expect(document.getElementById('a11y-live-region')?.textContent).toBe(en.nav.uiMode.announceFull)
  })
})
