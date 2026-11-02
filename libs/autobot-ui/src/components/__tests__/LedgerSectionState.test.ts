// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// LedgerSectionState (#18391): an unreadable ledger section must never read
// like an empty one, in either console.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import LedgerSectionState from '../LedgerSectionState.vue'
import type { LedgerSection } from '../../utils/ledger'

const labels = {
  loading: 'Reading',
  unavailableTitle: "Couldn't read",
  unavailableBody: (source: string) => `store ${source} did not answer`,
  errorTitle: 'Went wrong',
}

function render(section: LedgerSection<unknown>) {
  return mount(LedgerSectionState, {
    props: { section, empty: 'No claims', labels },
    slots: { default: '<p data-testid="rows">rows</p>' },
  })
}

describe('LedgerSectionState', () => {
  it('says loading while the section is read', () => {
    const w = render({ state: 'loading', rows: [] })
    expect(w.get('[data-testid="ledger-loading"]').text()).toBe('Reading')
  })

  it('names the store that did not answer, as an alert, not the empty line', () => {
    const w = render({ state: 'unavailable', rows: [], source: 'claims' })
    const alert = w.get('[data-testid="ledger-unavailable"]')
    expect(alert.attributes('role')).toBe('alert')
    expect(alert.text()).toContain('store claims did not answer')
    expect(w.find('[data-testid="ledger-empty"]').exists()).toBe(false)
  })

  it('shows a dash when the 503 named no store', () => {
    expect(render({ state: 'unavailable', rows: [] }).text()).toContain('store — did not answer')
  })

  it('reports an error apart from unavailable', () => {
    const w = render({ state: 'error', rows: [] })
    expect(w.get('[data-testid="ledger-error"]').text()).toBe('Went wrong')
    expect(w.find('[data-testid="ledger-unavailable"]').exists()).toBe(false)
  })

  it('says empty only for a section that was read and holds nothing', () => {
    const w = render({ state: 'ready', rows: [] })
    expect(w.get('[data-testid="ledger-empty"]').text()).toContain('No claims')
    expect(w.find('[data-testid="rows"]').exists()).toBe(false)
  })

  it('renders the rows slot for a ready section with rows', () => {
    const w = render({ state: 'ready', rows: [1] })
    expect(w.find('[data-testid="rows"]').exists()).toBe(true)
    expect(w.find('[data-testid="ledger-empty"]').exists()).toBe(false)
  })
})
