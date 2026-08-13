// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// #13942: the executor rollup panel must render the exact counts its matrix
// carries — never merely "mounts without crashing" — and must never render a
// failed fetch as a zero count (#14064's family).

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

import ExecutorRollupPanel from '../ExecutorRollupPanel.vue'
import { buildExecutorRollupMatrix } from '@/composables/llc/executorRollup'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages: { en },
  missingWarn: false,
  fallbackWarn: false,
})

const mountOpts = { global: { plugins: [i18n] } }

describe('ExecutorRollupPanel (#13942)', () => {
  it('renders the exact per-class totals and per-cell counts the matrix carries', () => {
    const matrix = buildExecutorRollupMatrix([
      { executor_class: 'user', status: 'backlog', count: 2 },
      { executor_class: 'user', status: 'done', count: 1 },
      { executor_class: 'agent', status: 'in_progress', count: 4 },
      { executor_class: 'unassigned', status: 'backlog', count: 3 },
    ])
    const wrapper = mount(ExecutorRollupPanel, {
      props: { matrix, loading: false, unavailable: false },
      ...mountOpts,
    })

    expect(wrapper.get('[data-testid="executor-rollup-total-user"]').text()).toBe('3')
    expect(wrapper.get('[data-testid="executor-rollup-total-agent"]').text()).toBe('4')
    expect(wrapper.get('[data-testid="executor-rollup-total-unassigned"]').text()).toBe('3')
    expect(wrapper.get('[data-testid="executor-rollup-total"]').text()).toContain('10')

    expect(wrapper.get('[data-testid="executor-rollup-cell-user-backlog"]').text()).toBe('2')
    expect(wrapper.get('[data-testid="executor-rollup-cell-user-done"]').text()).toBe('1')
    expect(wrapper.get('[data-testid="executor-rollup-cell-agent-in_progress"]').text()).toBe('4')
    expect(wrapper.get('[data-testid="executor-rollup-cell-unassigned-backlog"]').text()).toBe('3')
    // A cell with no data renders as an explicit 0, never a blank cell.
    expect(wrapper.get('[data-testid="executor-rollup-cell-agent-backlog"]').text()).toBe('0')
  })

  it('shows the unassigned bucket even when it is zero — it is never hidden as a non-finding', () => {
    const matrix = buildExecutorRollupMatrix([{ executor_class: 'user', status: 'backlog', count: 1 }])
    const wrapper = mount(ExecutorRollupPanel, {
      props: { matrix, loading: false, unavailable: false },
      ...mountOpts,
    })

    expect(wrapper.find('[data-testid="executor-rollup-legend-unassigned"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="executor-rollup-total-unassigned"]').text()).toBe('0')
  })

  it('never renders a zero count when the fetch failed — it renders the unavailable state', () => {
    const matrix = buildExecutorRollupMatrix([])
    const wrapper = mount(ExecutorRollupPanel, {
      props: { matrix, loading: false, unavailable: true },
      ...mountOpts,
    })

    expect(wrapper.find('[data-testid="executor-rollup-unavailable"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="executor-rollup-legend"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="executor-rollup-total"]').exists()).toBe(false)
  })

  it('renders the loading state, not an empty-looking panel, while the fetch is in flight', () => {
    const wrapper = mount(ExecutorRollupPanel, {
      props: { matrix: buildExecutorRollupMatrix([]), loading: true, unavailable: false },
      ...mountOpts,
    })

    expect(wrapper.find('[data-testid="executor-rollup-loading"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="executor-rollup-legend"]').exists()).toBe(false)
  })

  it('renders the honest empty state for a company with genuinely zero work items', () => {
    const wrapper = mount(ExecutorRollupPanel, {
      props: { matrix: buildExecutorRollupMatrix([]), loading: false, unavailable: false },
      ...mountOpts,
    })

    expect(wrapper.find('[data-testid="executor-rollup-empty"]').exists()).toBe(true)
    // The legend still renders (all-zero totals), distinguishing "loaded, empty" from "did not load".
    expect(wrapper.find('[data-testid="executor-rollup-legend"]').exists()).toBe(true)
  })
})
