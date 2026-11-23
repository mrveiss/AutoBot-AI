// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #22017 / #21961: the active sidebar item's indicator width is the `--nav-on-bw` token, so the
 * contrast theme draws 4px and light, dark and mono draw 2px. Vitest cannot lay out Tailwind, so
 * the per-theme width is resolved the way the cascade does: the theme's own `--nav-on-bw`
 * declaration in slm-scheme.css, applied to the width the rendered item names.
 */

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, reactive } from 'vue'
import Sidebar from './Sidebar.vue'

const auth = reactive({ isAuthenticated: false, isAdmin: true, logout: vi.fn() })

// @autobot/ui drags in reka-ui, which does not load under vitest here: stand in for what Sidebar uses.
vi.mock('@autobot/ui', () => ({
  BrandMark: defineComponent({ setup: () => () => h('span') }),
  usePollingJob: () => ({ start: vi.fn() }),
  useAnnounce: () => ({ announce: vi.fn() }),
  useFocusTrap: () => ({}),
}))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
vi.mock('@/components/common/LanguageSwitcher.vue', () => ({
  default: defineComponent({ setup: () => () => h('span') }),
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/fleet' }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/stores/fleet', () => ({
  useFleetStore: () => ({ overallHealth: 'healthy', fleetSummary: {} }),
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))
vi.mock('@/composables/useCodeSync', () => ({
  useCodeSync: () => ({ outdatedCount: { value: 0 }, fetchStatus: vi.fn() }),
}))
vi.mock('@/composables/useSystemUpdates', () => ({
  useSystemUpdates: () => ({ updateCount: { value: 0 }, fetchSummary: vi.fn() }),
}))
vi.mock('@/composables/useSlmTheme', () => ({
  useSlmTheme: () => ({ isContrast: { value: false }, toggleContrast: vi.fn() }),
}))


const SCHEME = readFileSync(resolve(__dirname, '../../assets/styles/slm-scheme.css'), 'utf-8')
const WIDTH_UTILITY = 'border-l-(length:--nav-on-bw)'

/** The `--nav-on-bw` a theme declares: the block whose selector names that theme. */
function themeWidth(theme: string): string {
  const block = new RegExp(`\\[data-theme='${theme}'\\]\\s*\\{([^}]*)\\}`).exec(SCHEME)
  const width = block && /--nav-on-bw:\s*([^;]+);/.exec(block[1])
  if (!width) throw new Error(`no --nav-on-bw declared for theme ${theme}`)
  return width[1].trim()
}

/** The width a rendered item draws: its class names the token, the theme supplies the value. */
function renderedWidth(el: Element, theme: string): string | null {
  return el.classList.contains(WIDTH_UTILITY) ? themeWidth(theme) : null
}

function activeAndIdle() {
  const wrapper = mount(Sidebar, { attachTo: document.body, global: { mocks: { $t: (key: string) => key } } })
  const all = wrapper.findAll('[role="menuitem"]').map((w) => w.element)
  const active = all.find((el) => el.getAttribute('aria-current') === 'page')
  const idle = all.find((el) => el.getAttribute('aria-current') !== 'page')
  return { wrapper, active, idle }
}

describe('Sidebar active indicator width (#22017)', () => {
  it.each([
    ['light', '2px'],
    ['dark', '2px'],
    ['mono', '2px'],
    ['contrast', '4px'],
  ])('%s theme renders a %s active indicator', (theme, width) => {
    auth.isAdmin = true
    const { wrapper, active } = activeAndIdle()
    expect(active).toBeDefined()
    expect(renderedWidth(active as Element, theme)).toBe(width)
    wrapper.unmount()
  })

  it('draws the same width on idle items, so selecting one does not shift the layout', () => {
    auth.isAdmin = true
    const { wrapper, idle } = activeAndIdle()
    expect((idle as Element).classList.contains(WIDTH_UTILITY)).toBe(true)
    expect((idle as Element).classList.contains('border-transparent')).toBe(true)
    wrapper.unmount()
  })

  it('names no literal border width on the item', () => {
    auth.isAdmin = true
    const { wrapper, active } = activeAndIdle()
    expect(Array.from((active as Element).classList).filter((c) => /^border-l(-\d+)?$/.test(c))).toEqual([])
    wrapper.unmount()
  })
})

describe('slm-scheme.css --nav-on-bw consumers (#22017)', () => {
  it('is read by the sidebar, the only SLM navigation', () => {
    expect(readFileSync(resolve(__dirname, 'Sidebar.vue'), 'utf-8')).toContain('--nav-on-bw')
  })
})
