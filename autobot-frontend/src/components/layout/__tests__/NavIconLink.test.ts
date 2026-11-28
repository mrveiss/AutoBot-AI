// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * NavIconLink (#18240): aria-label names the control, so the tooltip is linked
 * with aria-describedby only where it says something the name does not.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createRouter, createMemoryHistory } from 'vue-router'
import NavIconLink from '../NavIconLink.vue'
import type { NavIconItem } from '@/config/navItems'

const messages = {
  en: { name: 'Preferences', same: 'preferences ', longer: 'Secrets — stored keys' },
}
const i18n = createI18n({ legacy: false, locale: 'en', messages })
const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)*', component: { render: () => null } }] })

function mountLink(tipKey: string, extra: Partial<NavIconItem> = {}) {
  const item = { to: '/x', labelKey: 'name', ariaKey: 'name', tipKey, iconPaths: ['M0 0'], ...extra } as NavIconItem
  return mount(NavIconLink, { props: { item }, global: { plugins: [i18n, router] } })
}

beforeEach(() => {
  document.body.innerHTML = ''
})

describe('NavIconLink aria-describedby', () => {
  it('is omitted when the tooltip repeats the accessible name', () => {
    const a = mountLink('same').get('a')
    expect(a.attributes('aria-label')).toBe('Preferences')
    expect(a.attributes('aria-describedby')).toBeUndefined()
  })

  it('is kept when the tooltip adds information', () => {
    const a = mountLink('longer').get('a')
    expect(a.attributes('aria-describedby')).toMatch(/^aui-tooltip-/)
  })

  it('follows the same rule for an external link', () => {
    const href = () => 'https://example.invalid/'
    expect(mountLink('same', { to: undefined, href }).get('a').attributes('aria-describedby')).toBeUndefined()
    expect(mountLink('longer', { to: undefined, href }).get('a').attributes('aria-describedby')).toBeTruthy()
  })
})
