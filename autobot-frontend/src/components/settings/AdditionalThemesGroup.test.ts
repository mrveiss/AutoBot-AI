// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AdditionalThemesGroup (#18240): SLM-deployed themes from the installed-theme
 * registry, each badged "Deployed via SLM", plus the link to the SLM console.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

vi.mock('@/composables/useThemeRegistry', () => ({
  fetchInstalledThemes: () =>
    Promise.resolve([{ id: 'aqua', name: 'Aqua', author: 'Northwind', version: '1.2', supports: [] }]),
}))

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

async function mountGroup() {
  vi.resetModules()
  const { default: Group } = await import('./AdditionalThemesGroup.vue')
  const { useThemeVariant } = await import('@/composables/useThemeVariant')
  await useThemeVariant().loadInstalledThemes()
  const wrapper = mount(Group, { global: { plugins: [i18n] } })
  await flushPromises()
  return { wrapper, variant: useThemeVariant() }
}

beforeEach(() => {
  localStorage.clear()
})

describe('AdditionalThemesGroup', () => {
  it('lists a deployed theme with its Deployed via SLM badge and version', async () => {
    const { wrapper } = await mountGroup()
    const card = wrapper.get('[data-testid="additional-theme-aqua"]')
    expect(card.text()).toContain('Aqua')
    expect(card.text()).toContain('Deployed via SLM · v1.2')
    expect(card.attributes('aria-pressed')).toBe('false')
  })

  it('links to the SLM console in a new tab, safely', async () => {
    const { wrapper } = await mountGroup()
    const link = wrapper.get('a[target="_blank"]')
    expect(link.attributes('rel')).toContain('noopener')
    expect(link.text()).toBe(en.settings.additionalThemes.slmLink)
  })
})
