// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// MovedToUserApp (#20644): an old console path for Vision or Batch Processing says where the screen
// went and links to it in the user app.

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en.json'

vi.mock('@/config/ssot-config', () => ({ getUserAppUrl: () => 'https://user-app.example' }))
vi.mock('@autobot/ui', () => ({
  EmptyState: { props: ['title', 'description'], template: '<div><h2>{{ title }}</h2><p>{{ description }}</p><slot name="actions" /></div>' },
  BaseButton: { props: ['as'], template: '<a v-bind="$attrs"><slot /></a>' },
}))

import MovedToUserApp from './MovedToUserApp.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
const mountFor = (screen: 'batch' | 'vision') =>
  mount(MovedToUserApp, { props: { screen }, global: { plugins: [i18n] } })

describe('MovedToUserApp (#20644)', () => {
  it.each([
    ['batch', 'Batch Processing', 'https://user-app.example/batch'],
    ['vision', 'Vision', 'https://user-app.example/vision'],
  ] as const)('%s: says where it moved and links there', (screen, name, href) => {
    const wrapper = mountFor(screen)
    expect(wrapper.get('h2').text()).toBe(`${name} moved to the user app`)
    const link = wrapper.get('a')
    expect(link.attributes('href')).toBe(href)
    expect(link.attributes('target')).toBe('_blank')
    expect(link.text()).toBe(`Open ${name} in the user app`)
  })
})
