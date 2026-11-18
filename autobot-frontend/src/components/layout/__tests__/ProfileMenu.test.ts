// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * ProfileMenu (#18240): System status is a menu item now (the brand mark no
 * longer opens it), and the admin/canvas items are kept.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import en from '@/i18n/locales/en.json'
import ProfileMenu from '../ProfileMenu.vue'
import { useUserStore } from '@/stores/useUserStore'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div />' } }] })

async function openMenu(role: 'admin' | 'user') {
  setActivePinia(createPinia())
  const user = useUserStore()
  user.currentUser = { id: '1', username: 'jane', role } as never
  user.authState = { isAuthenticated: true, token: 't' } as never
  const wrapper = mount(ProfileMenu, { attachTo: document.body, global: { plugins: [i18n, router] } })
  await wrapper.get('[data-testid="profile-menu-trigger"]').trigger('click')
  await wrapper.vm.$nextTick()
  return wrapper
}

beforeEach(() => {
  document.body.innerHTML = ''
})

describe('ProfileMenu', () => {
  it('names the avatar button by i18n and offers Profile settings, System status and About', async () => {
    const wrapper = await openMenu('user')
    expect(wrapper.get('[data-testid="profile-menu-trigger"]').attributes('aria-label')).toBe(en.nav.profileMenu)
    const items = [...document.querySelectorAll('[role="menuitem"]')].map((el) => el.textContent?.trim())
    expect(items).toEqual(expect.arrayContaining([en.nav.profileSettings, en.nav.systemStatus, en.nav.about]))
  })

  it('System status emits open-status and closes the menu', async () => {
    const wrapper = await openMenu('user')
    ;(document.querySelector('[data-testid="profile-menu-status"]') as HTMLButtonElement).click()
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('open-status')).toHaveLength(1)
    expect(document.querySelector('[role="menu"]')).toBeNull()
  })

  it('shows the admin section to an admin', async () => {
    await openMenu('admin')
    expect(document.body.textContent).toContain(en.nav.adminPanel)
  })

  it('hides the admin section from a non-admin', async () => {
    await openMenu('user')
    expect(document.body.textContent).not.toContain(en.nav.adminPanel)
  })
})
