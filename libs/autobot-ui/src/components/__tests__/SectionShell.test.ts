// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// SectionShell (#22019 AC3): sidebar + content, the drawer toggle and its labels, the backdrop,
// and the nav-link click that closes an open drawer on a narrow viewport.

import { describe, it, expect, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import SectionShell from '../SectionShell.vue'

const SECTIONS = [{ id: 's', label: 'Browse', items: [{ id: 'a', label: 'Browser', to: '/browser', active: true }] }]

const render = (props: Record<string, unknown> = {}) =>
  mount(SectionShell, {
    props: { navLabel: 'Nav', sections: SECTIONS, openLabel: 'Open', closeLabel: 'Close', ...props },
    slots: { default: '<p class="body">content</p>', 'toggle-icon': '<i class="ti" />' },
  })

const setWidth = (w: number) => Object.defineProperty(window, 'innerWidth', { value: w, configurable: true })

describe('SectionShell', () => {
  afterEach(() => setWidth(1024))

  it('renders the nav and the content slot', () => {
    const w = render()
    expect(w.find('nav[aria-label="Nav"]').exists()).toBe(true)
    expect(w.find('main .body').text()).toBe('content')
  })

  it('labels the toggle by state and emits the opposite', async () => {
    const w = render()
    const toggle = w.get('.aui-section-shell__toggle')
    expect(toggle.attributes('aria-label')).toBe('Open')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    await toggle.trigger('click')
    expect(w.emitted('update:open')?.[0]).toEqual([true])
  })

  it('shows the backdrop when open and closes on its click', async () => {
    const w = render({ open: true })
    expect(w.get('.aui-section-shell__toggle').attributes('aria-label')).toBe('Close')
    await w.get('.aui-section-shell__overlay').trigger('click')
    expect(w.emitted('update:open')?.[0]).toEqual([false])
  })

  it('closes an open drawer on a nav link click only when narrow', async () => {
    const w = render({ open: true })
    setWidth(1024)
    await w.get('a').trigger('click')
    expect(w.emitted('update:open')).toBeUndefined()
    setWidth(500)
    await w.get('a').trigger('click')
    expect(w.emitted('update:open')?.[0]).toEqual([false])
  })
})
