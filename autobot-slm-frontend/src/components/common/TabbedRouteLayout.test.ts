// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import TabbedRouteLayout from './TabbedRouteLayout.vue'

const push = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/x/b' }),
  useRouter: () => ({ push }),
}))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))
vi.mock('@autobot/ui', () => ({ PollingPausedAlert: { template: '<div class="alert" />' } }))

const tabs = [
  { id: 'a', label: 'A', path: '/x/a', icon: 'M0 0' },
  { id: 'b', label: 'B', path: '/x/b', icon: 'M0 0' },
]

function build() {
  return mount(TabbedRouteLayout, {
    props: { title: 'T', tabsLabel: 'Sections', tabs, defaultTab: 'a', poller: {} as never },
    slots: { 'tab-badge': '<i class="badge" />' },
    global: { stubs: { 'router-view': true } },
  })
}

describe('TabbedRouteLayout', () => {
  it('marks the tab matching the route selected and exposes the tablist label', () => {
    const w = build()
    const btns = w.findAll('[role="tab"]')
    expect(btns.map(b => b.attributes('aria-selected'))).toEqual(['false', 'true'])
    expect(w.find('[role="tablist"]').attributes('aria-label')).toBe('Sections')
    expect(w.findAll('.badge')).toHaveLength(2)
  })

  it('navigates on tab click', async () => {
    await build().findAll('[role="tab"]')[0].trigger('click')
    expect(push).toHaveBeenCalledWith('/x/a')
  })
})
