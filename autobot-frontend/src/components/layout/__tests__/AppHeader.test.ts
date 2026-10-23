// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AppHeader (#18240): the brand is the kit mark linking Home, the Plugins icon
 * and the SLM text link are gone, Platform admin is a gated external shield,
 * and every icon carries an accessible name and a tooltip.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import en from '@/i18n/locales/en.json'
import AppHeader from '../AppHeader.vue'
import { useSystemStatus } from '@/composables/useSystemStatus'
import { SYSTEM_STATUS_KEY } from '@/composables/systemStatusContext'
import { useUiMode } from '@/composables/useUiMode'
import { useUserStore } from '@/stores/useUserStore'
import { getSLMAdminUrl } from '@/config/ssot-config'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const stub = { template: '<div />' }
const router = createRouter({
  history: createMemoryHistory(),
  routes: ['/home', '/chat', '/knowledge', '/analytics', '/automation', '/secrets', '/preferences', '/about'].map(
    (path) => ({ path, component: stub }),
  ),
})

async function mountHeader(role: 'admin' | 'user'): Promise<VueWrapper> {
  setActivePinia(createPinia())
  const user = useUserStore()
  user.currentUser = { id: '1', username: 'jane', role } as never
  await router.push('/home')
  await router.isReady()
  return mount(AppHeader, {
    attachTo: document.body,
    global: { plugins: [i18n, router], provide: { [SYSTEM_STATUS_KEY as symbol]: useSystemStatus() } },
  })
}

beforeEach(() => {
  document.body.innerHTML = ''
  localStorage.clear()
  useUiMode().setMode('full')
})

describe('AppHeader brand', () => {
  it('is the kit mark linking Home, named by i18n, with an aria-hidden health dot', async () => {
    const wrapper = await mountHeader('admin')
    const brand = wrapper.get('[data-testid="app-brand"]')
    expect(brand.attributes('href')).toBe('/home')
    expect(brand.attributes('aria-label')).toBe(en.nav.homeAria)
    expect(brand.find('.aui-brand-mark').exists()).toBe(true)
    expect(wrapper.get('[data-testid="health-dot"]').attributes('aria-hidden')).toBe('true')
  })
})

describe('AppHeader icon cluster', () => {
  it('has no Plugins icon and no SLM text link', async () => {
    const wrapper = await mountHeader('admin')
    expect(wrapper.find('a[href="/plugins"]').exists()).toBe(false)
    expect(wrapper.text()).not.toMatch(/Plugins/)
    expect(wrapper.text()).not.toMatch(/SLM Admin/)
  })

  it('shows the Platform admin shield to a role with service.management, opening a new tab safely', async () => {
    const wrapper = await mountHeader('admin')
    const shield = wrapper.get(`a[aria-label="${en.nav.platformAdminAria}"]`)
    expect(shield.attributes('href')).toBe(getSLMAdminUrl())
    expect(shield.attributes('target')).toBe('_blank')
    expect(shield.attributes('rel')).toContain('noopener')
  })

  it('hides the shield from a role without service.management', async () => {
    const wrapper = await mountHeader('user')
    expect(wrapper.find(`a[aria-label="${en.nav.platformAdminAria}"]`).exists()).toBe(false)
  })

  it('gives every icon an aria-label and a tooltip, described by it only where the tip adds to the name', async () => {
    const wrapper = await mountHeader('admin')
    const controls = wrapper.get('[data-testid="nav-icon-cluster"]').findAll('a, button')
    expect(controls.length).toBeGreaterThanOrEqual(4)
    for (const control of controls) {
      const name = control.attributes('aria-label') ?? control.text()
      expect(name.length, 'accessible name').toBeGreaterThan(0)
      const describedby = control.attributes('aria-describedby')
      if (name === en.nav.preferences) {
        expect(describedby, 'tip repeats the name').toBeUndefined() // not read twice
        continue
      }
      const tip = document.getElementById(describedby ?? '')
      expect(tip?.getAttribute('role')).toBe('tooltip')
      expect(tip?.textContent?.trim().length).toBeGreaterThan(0)
    }
  })

  it('marks advanced icons .adv so Minimal hides them, and keeps Preferences', async () => {
    const wrapper = await mountHeader('admin')
    const adv = wrapper.findAll('[data-testid="nav-icon-cluster"] .adv')
    expect(adv.length).toBe(2)
    const prefs = wrapper.get(`a[aria-label="${en.nav.preferences}"]`)
    expect(prefs.element.closest('.adv')).toBeNull()
  })
})

describe('AppHeader links', () => {
  it('lists the primary links; Automation lives in the More menu, not on the rail', async () => {
    const wrapper = await mountHeader('admin')
    const rail = wrapper.findAll('[data-nav-item]').map((a) => a.attributes('href'))
    expect(rail).toEqual(expect.arrayContaining(['/home', '/chat', '/knowledge', '/analytics']))
    expect(rail).not.toContain('/automation')
    expect(wrapper.find(`button[aria-label="${en.nav.moreItems}"]`).exists()).toBe(true)
  })

  it('drops advanced links in Minimal mode', async () => {
    useUiMode().setMode('minimal')
    const wrapper = await mountHeader('admin')
    const rail = wrapper.findAll('[data-nav-item]').map((a) => a.attributes('href'))
    expect(rail).not.toContain('/analytics')
    expect(wrapper.find(`button[aria-label="${en.nav.moreItems}"]`).exists()).toBe(false)
  })

  it('marks the active link with aria-current', async () => {
    const wrapper = await mountHeader('admin')
    expect(wrapper.get('[data-nav-item][href="/home"]').attributes('aria-current')).toBe('page')
    expect(wrapper.get('[data-nav-item][href="/chat"]').attributes('aria-current')).toBeUndefined()
  })
})
