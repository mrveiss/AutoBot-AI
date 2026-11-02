// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Breadcrumb (#17563): a named nav landmark with an ordered list; every item but the last is a
// link, through the caller's link component when given; the last item is the current page.

import { describe, it, expect } from 'vitest'
import { h } from 'vue'
import { mount } from '@vue/test-utils'
import Breadcrumb from '../Breadcrumb.vue'

const items = [
  { label: 'Portfolios', to: '/llc' },
  { label: 'Platform', to: '/llc/p/1' },
  { label: 'Release 2' },
]

describe('Breadcrumb', () => {
  it('is a nav landmark named by the app', () => {
    const w = mount(Breadcrumb, { props: { items, label: 'Trail' } })
    expect(w.find('nav').attributes('aria-label')).toBe('Trail')
    expect(w.findAll('ol > li')).toHaveLength(3)
  })

  it('links every item but the last, as plain anchors by default', () => {
    const w = mount(Breadcrumb, { props: { items, label: 'Trail' } })
    const links = w.findAll('a')
    expect(links.map((a) => a.attributes('href'))).toEqual(['/llc', '/llc/p/1'])
    const current = w.find('[aria-current="page"]')
    expect(current.text()).toBe('Release 2')
    expect(current.element.tagName).toBe('SPAN')
  })

  it('renders the current page as text even when it has a target', () => {
    const w = mount(Breadcrumb, { props: { items: [{ label: 'Home', to: '/' }, { label: 'Here', to: '/here' }], label: 'Trail' } })
    expect(w.findAll('a')).toHaveLength(1)
    expect(w.find('[aria-current="page"]').text()).toBe('Here')
  })

  it('passes `to` to the caller link component (RouterLink without a router import)', () => {
    // fails if the kit stops accepting a component, which is how callers supply RouterLink
    const LinkLike = { props: ['to'], setup: (p: { to: string }, { slots }: { slots: Record<string, () => unknown> }) => () => h('a', { 'data-to': p.to }, slots.default?.() as never) }
    const w = mount(Breadcrumb, { props: { items, label: 'Trail', linkAs: LinkLike } })
    expect(w.findAll('a').map((a) => a.attributes('data-to'))).toEqual(['/llc', '/llc/p/1'])
  })

  it('hides the separators from assistive technology', () => {
    const w = mount(Breadcrumb, { props: { items, label: 'Trail' } })
    const seps = w.findAll('.aui-breadcrumb__sep')
    expect(seps).toHaveLength(2)
    seps.forEach((s) => expect(s.attributes('aria-hidden')).toBe('true'))
  })

  it('a selectable item is a button that emits its index; the current page is not', async () => {
    const w = mount(Breadcrumb, {
      props: { label: 'Path', items: [{ label: 'Home', selectable: true }, { label: 'src', selectable: true }, { label: 'app', selectable: true }] },
    })
    const buttons = w.findAll('button')
    expect(buttons.map((b) => b.text())).toEqual(['Home', 'src'])
    buttons.forEach((b) => expect(b.attributes('type')).toBe('button'))
    await buttons[1].trigger('click')
    expect(w.emitted('select')).toEqual([[1]])
    expect(w.find('[aria-current="page"]').text()).toBe('app')
  })

  it('takes item content and the separator from slots', () => {
    const w = mount(Breadcrumb, {
      props: { items, label: 'Trail' },
      slots: {
        item: '<template #item="{ item, index }"><i class="glyph" />{{ index }}:{{ item.label }}</template>',
        separator: '<b class="chev" />',
      },
    })
    expect(w.findAll('.glyph')).toHaveLength(3)
    expect(w.find('[aria-current="page"]').text()).toBe('2:Release 2')
    expect(w.findAll('.aui-breadcrumb__sep .chev')).toHaveLength(2)
  })
})
