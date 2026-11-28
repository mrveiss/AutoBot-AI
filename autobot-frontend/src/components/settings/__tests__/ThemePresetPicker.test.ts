// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * ThemePresetPicker: a fresh install highlights no preset (#18252), and the preset
 * names and header come from i18n keys (#18255).
 */
import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

function stubMatchMedia(): void {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  })
}

async function mountPicker() {
  vi.resetModules()
  const { initializeTheme } = await import('@/composables/useTheme')
  initializeTheme()
  const { default: ThemePresetPicker } = await import('../ThemePresetPicker.vue')
  const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
  // The installed-themes group fetches from the backend; it is not under test here.
  return mount(ThemePresetPicker, {
    global: { plugins: [i18n], stubs: { AdditionalThemesGroup: true } },
  })
}

/**
 * Each test resets modules and re-imports the picker. The first import pays the cold
 * transform of the whole graph, which under a loaded pre-push outran the default 10 s
 * timeout. Warm it once here with its own budget, as usePreferences.account.test.ts
 * does (#18254), so each test measures only its own work.
 */
const COLD_IMPORT_MS = 60_000
beforeAll(async () => {
  await Promise.all([import('@/composables/useTheme'), import('../ThemePresetPicker.vue')])
}, COLD_IMPORT_MS)

describe('ThemePresetPicker', () => {
  beforeEach(() => {
    localStorage.clear()
    stubMatchMedia()
  })

  it('highlights no preset on a fresh install', async () => {
    const wrapper = await mountPicker()
    expect(wrapper.findAll('.preset-card.active')).toHaveLength(0)
    expect(wrapper.findAll('.preset-card[aria-pressed="true"]')).toHaveLength(0)
  })

  it('highlights the stored named preset', async () => {
    localStorage.setItem('autobot-theme-preset', 'midnight')
    const wrapper = await mountPicker()
    const active = wrapper.findAll('.preset-card.active')
    expect(active).toHaveLength(1)
    expect(active[0].text()).toContain(en.ui.themePresets.names.midnight)
  })

  it('a picked preset becomes the one highlight, and a manual base theme clears it', async () => {
    const wrapper = await mountPicker()
    const autoCard = wrapper.findAll('.preset-card').find((c) => c.text().includes(en.ui.themePresets.names.auto))
    await autoCard!.trigger('click')
    expect(wrapper.findAll('.preset-card.active')).toHaveLength(1)
    expect(autoCard!.attributes('aria-pressed')).toBe('true')

    const darkButton = wrapper.findAll('.option-btn').find((b) => b.text().includes(en.ui.themeToggle.dark))
    await darkButton!.trigger('click')
    expect(wrapper.findAll('.preset-card.active')).toHaveLength(0)
  })

  it('renders the header and preset names from en.json', async () => {
    const wrapper = await mountPicker()
    expect(wrapper.find('.picker-title').text()).toContain(en.ui.themePresets.title)
    expect(wrapper.text()).toContain(en.ui.themePresets.descriptions['high-contrast-dark'])
    // No i18n key path renders raw, whichever namespace it is in
    expect(wrapper.text()).not.toMatch(/\bui\.[a-zA-Z]+\.[a-zA-Z]/)
  })
})
