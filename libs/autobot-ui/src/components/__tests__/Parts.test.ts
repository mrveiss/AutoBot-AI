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
import BaseInput from '../BaseInput.vue'
import EmptyState from '../EmptyState.vue'
import BaseButton from '../BaseButton.vue'
import BaseBadge from '../BaseBadge.vue'
import cardSrc from '../BaseCard.vue?raw'
import tableSrc from '../BaseTable.vue?raw'
import headerSrc from '../PageHeader.vue?raw'
import inputSrc from '../BaseInput.vue?raw'
import emptySrc from '../EmptyState.vue?raw'
import buttonSrc from '../BaseButton.vue?raw'
import badgeSrc from '../BaseBadge.vue?raw'

// The root's own part plus every descendant's, once each (find may or may not include the root).
const slots = (w: ReturnType<typeof mount>): string[] =>
  [...new Set([w.attributes('data-slot'), ...w.findAll('[data-slot]').map((e) => e.attributes('data-slot'))])]

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
    expect(slots(w)).toEqual(['card', 'card-body'])
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

/** A selector that styles an element part (or the root) by class: modifiers (`--x`) are not matched. */
const partClassSelector = (prefix: string): RegExp =>
  new RegExp(`\\.${prefix}(?:__[a-z]+(?:-[a-z]+)*)?(?![\\w-])\\s*[{,:\\[>+~]|\\.${prefix}(?:__[a-z]+(?:-[a-z]+)*)?(?![\\w-])\\s+[.\\[a-z]`)

const PARTS: Record<string, { prefix: string; source: string; parts: string[] }> = {
  BaseCard: { prefix: "aui-card", source: cardSrc, parts: ["card", "card-header", "card-heading", "card-title", "card-subtitle", "card-actions", "card-body", "card-footer"] },
  BaseTable: { prefix: "aui-table", source: tableSrc, parts: ["table", "table-controls", "table-tools", "table-sr", "table-scroll", "table-grid", "table-caption", "table-head-cell", "table-check", "table-checkbox", "table-sort", "table-arrow", "table-row", "table-cell", "table-state", "table-footer"] },
  PageHeader: { prefix: "aui-page-header", source: headerSrc, parts: ["page-header", "page-header-breadcrumb", "page-header-row", "page-header-start", "page-header-text", "page-header-eyebrow", "page-header-title", "page-header-title-text", "page-header-subtitle", "page-header-actions", "page-header-toolbar"] },
  BaseInput: { prefix: "aui-input", source: inputSrc, parts: ["input", "input-label", "input-asterisk", "input-control", "input-affix", "input-field", "input-clear", "input-error", "input-helper"] },
  EmptyState: { prefix: "aui-empty", source: emptySrc, parts: ["empty", "empty-icon", "empty-title", "empty-description", "empty-actions"] },
  BaseButton: { prefix: "aui-btn", source: buttonSrc, parts: ["button", "button-label", "button-spinner"] },
  BaseBadge: { prefix: "aui-badge", source: badgeSrc, parts: ["badge", "badge-remove"] },
}

const mountAll = () => ({
  BaseInput: mount(BaseInput, { props: { label: 'L', modelValue: 'v', required: true, error: 'e', clearable: true }, slots: { prefix: () => h('i'), suffix: () => h('i') } }),
  EmptyState: mount(EmptyState, { props: { title: 'T', description: 'D' }, slots: { icon: () => h('i'), actions: () => h('i') } }),
  BaseButton: mount(BaseButton, { props: { loading: true }, slots: { default: 'x' } }),
  BaseBadge: mount(BaseBadge, { props: { label: 'x', removable: true, removeLabel: 'r' } }),
})

describe('part names, every kit primitive (#17564, #14776, #14778)', () => {
  it.each(Object.entries(PARTS))('%s declares exactly its documented parts', (_name, { source, parts }) => {
    const template = source.split('<style')[0]
    const found = [...new Set([...template.matchAll(/data-slot="([a-z-]+)"/g)].map((m) => m[1]))].sort()
    expect(found).toEqual([...parts].sort())
  })

  it.each(Object.entries(PARTS))('%s stylesheet targets its parts by data-slot, not by class', (_name, { prefix, source, parts }) => {
    const css = source.split('<style scoped>')[1]
    expect(css).toContain(`[data-slot="${parts[0]}"]`)
    expect(css.match(partClassSelector(prefix))).toBeNull()
  })

  it('the part-class pattern ignores modifier classes and catches a part class', () => {
    const re = partClassSelector('aui-card')
    expect('.aui-card__body--flush { padding: 0; }').not.toMatch(re)
    expect('.aui-card--sm [data-slot="card-body"] { x: y; }').not.toMatch(re)
    expect('.aui-card__body { padding: 0; }').toMatch(re)
    expect('.aui-card { display: flex; }').toMatch(re)
    expect('.aui-card--sm .aui-card__body {').toMatch(re)
  })

  it('BaseInput, EmptyState, BaseButton and BaseBadge render their parts', () => {
    const m = mountAll()
    const root = (w: ReturnType<typeof mount>) => [w.attributes('data-slot'), ...slots(w)]
    expect(root(m.BaseInput)).toEqual(expect.arrayContaining(['input', 'input-label', 'input-asterisk', 'input-control', 'input-affix', 'input-field', 'input-error']))
    expect(root(m.EmptyState)).toEqual(expect.arrayContaining(['empty', 'empty-icon', 'empty-title', 'empty-description', 'empty-actions']))
    expect(root(m.BaseButton)).toEqual(expect.arrayContaining(['button', 'button-label', 'button-spinner']))
    expect(root(m.BaseBadge)).toEqual(expect.arrayContaining(['badge', 'badge-remove']))
  })
})
