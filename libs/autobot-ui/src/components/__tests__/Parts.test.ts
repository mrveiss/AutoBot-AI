// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// #17564 AC5: the part names are public API. This pins them, so a rename is a test
// failure and therefore a deliberate, breaking change.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { h } from 'vue'
import BaseCard from '../BaseCard.vue'
import BaseTable from '../BaseTable.vue'
import PageHeader from '../PageHeader.vue'

const slots = (w: ReturnType<typeof mount>): string[] =>
  w.findAll('[data-slot]').map((e) => e.attributes('data-slot'))

describe('part names (#17564)', () => {
  it('BaseCard exposes card, header, heading, actions, body, footer', () => {
    const w = mount(BaseCard, {
      props: { title: 'T' },
      slots: { default: 'b', actions: () => h('span'), footer: () => h('span') },
    })
    expect([w.attributes('data-slot'), ...slots(w)]).toEqual(
      expect.arrayContaining(['card', 'card-header', 'card-heading', 'card-actions', 'card-body', 'card-footer']),
    )
  })

  it('BaseCard omits the parts it does not render', () => {
    const w = mount(BaseCard, { slots: { default: 'b' } })
    expect(slots(w)).toEqual(['card-body'])
  })

  it('BaseTable exposes table, scroll, head-cell, row, cell, footer', () => {
    const w = mount(BaseTable, {
      props: { columns: [{ key: 'a', label: 'A' }], rows: [{ id: 1, a: 1 }] },
      slots: { footer: () => h('span') },
    })
    expect([w.attributes('data-slot'), ...slots(w)]).toEqual(
      expect.arrayContaining(['table', 'table-scroll', 'table-head-cell', 'table-row', 'table-cell', 'table-footer']),
    )
  })

  it('BaseTable state cell carries table-state', () => {
    const w = mount(BaseTable, { props: { columns: [{ key: 'a', label: 'A' }], rows: [], loading: true, loadingLabel: 'L' } })
    expect(slots(w)).toContain('table-state')
  })

  it('PageHeader exposes page-header and its regions', () => {
    const w = mount(PageHeader, {
      props: { title: 'T' },
      slots: { breadcrumb: () => h('i'), actions: () => h('i'), default: () => h('i') },
    })
    expect([w.attributes('data-slot'), ...slots(w)]).toEqual(
      expect.arrayContaining([
        'page-header',
        'page-header-breadcrumb',
        'page-header-row',
        'page-header-actions',
        'page-header-toolbar',
      ]),
    )
  })
})
