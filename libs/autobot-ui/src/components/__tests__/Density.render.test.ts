// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// #17564 AC4: switching the density scope on an ancestor changes what the card and
// table primitives actually paint, with no prop change. The primitive's own rule is
// read for the token it consumes, then that token is resolved under each scope.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import cardSource from '../BaseCard.vue?raw'
import tableSource from '../BaseTable.vue?raw'
import BaseCard from '../BaseCard.vue'
import BaseTable from '../BaseTable.vue'
import { resolveToken, type Density } from './densityResolve'

const SCOPES: Density[] = ['compact', 'comfortable', 'spacious']

/** The value a part's rule gives `prop`, e.g. `var(--aui-card-padding)`. */
function ruleValue(source: string, slot: string, prop: string): string {
  const css = source.split('<style scoped>')[1]
  const rule = css.match(new RegExp(`\\[data-slot="${slot}"\\]\\s*\\{([^}]*)\\}`))
  const decl = rule?.[1].match(new RegExp(`(?:^|[\\s;])${prop}:\\s*([^;]+);`))
  if (!decl) throw new Error(`no ${prop} on [data-slot="${slot}"]`)
  return decl[1].trim()
}

const px = (v: string): number => (v.endsWith('rem') ? parseFloat(v) * 16 : parseFloat(v))
const tokenOf = (value: string): string => value.match(/var\((--[\w-]+)\)/)![1]
const sizes = (token: string) => SCOPES.map((s) => px(resolveToken(token, s)))

describe('density scope reaches the primitives (#17564)', () => {
  it('card body padding grows compact < comfortable < spacious', () => {
    const token = tokenOf(ruleValue(cardSource, 'card-body', 'padding'))
    expect(token).toBe('--aui-card-padding')
    const [compact, comfortable, spacious] = sizes(token)
    expect(compact).toBeLessThan(comfortable)
    expect(comfortable).toBeLessThan(spacious)
  })

  it('table row height and cell padding grow compact < comfortable < spacious', () => {
    const height = tokenOf(ruleValue(tableSource, 'table-cell', 'height'))
    const padding = ruleValue(tableSource, 'table-cell', 'padding')
    for (const token of [height, padding.match(/var\((--aui-table-cell-py)\)/)![1]]) {
      const [compact, comfortable, spacious] = sizes(token)
      expect(compact, token).toBeLessThan(comfortable)
      expect(comfortable, token).toBeLessThan(spacious)
    }
  })

  it('the comfortable values are the pre-density rendering', () => {
    expect(px(resolveToken('--aui-table-row-h', 'comfortable'))).toBe(44)
    expect(px(resolveToken('--aui-table-cell-py', 'comfortable'))).toBe(10)
    expect(px(resolveToken('--aui-card-padding', 'comfortable'))).toBe(16)
  })

  it('the same mounted markup is used in every scope: no prop carries density', () => {
    const card = mount(BaseCard, { props: { title: 'T' }, slots: { default: 'x' } })
    const table = mount(BaseTable, { props: { columns: [{ key: 'a', label: 'A' }], rows: [{ id: 1, a: 1 }] } })
    expect(card.find('[data-slot="card-body"]').exists()).toBe(true)
    expect(table.find('[data-slot="table-cell"]').exists()).toBe(true)
    expect(Object.keys(BaseCard.props ?? {})).not.toContain('density')
  })
})
