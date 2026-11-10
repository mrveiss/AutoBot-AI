// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #20917: the approvals icon carries the count of what is waiting, and nothing at zero.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createRouter, createMemoryHistory } from 'vue-router'
import NavIconLink from '../NavIconLink.vue'
import type { NavIconItem } from '@/config/navItems'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en: { name: 'Approvals', tip: 'Waiting' } } })
const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)*', component: { render: () => null } }] })
const item = { to: '/approvals', labelKey: 'name', ariaKey: 'name', tipKey: 'tip', iconPaths: ['M0 0'] } as NavIconItem

const mountWith = (badge?: number) =>
  mount(NavIconLink, { props: { item, badge }, global: { plugins: [i18n, router] } })

describe('NavIconLink badge (#20917)', () => {
  it('shows the count while it is above zero', () => {
    expect(mountWith(3).get('[data-testid="nav-badge"]').text()).toBe('3')
  })

  it('shows nothing at zero or when no count is given (control)', () => {
    expect(mountWith(0).find('[data-testid="nav-badge"]').exists()).toBe(false)
    expect(mountWith().find('[data-testid="nav-badge"]').exists()).toBe(false)
  })
})
