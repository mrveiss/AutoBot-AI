// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// SectionNav (#18241): sections and items, aria-current on the active item, `adv` and
// per-item class reaching the DOM, the link component, and the icon / trailing / footer slots.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import SectionNav from '../SectionNav.vue'

const SECTIONS = [
  {
    id: 'browse',
    label: 'Browse',
    items: [
      { id: 'browser', label: 'Browser', to: '/browser', active: true },
      { id: 'graph', label: 'Graph', to: '/graph', adv: true, class: 'extra' },
    ],
  },
  { id: 'adv-sect', label: 'Research', adv: true, items: [{ id: 'web', label: 'Web', to: '/web', adv: true }] },
]

const render = (props: Record<string, unknown> = {}, slots: Record<string, unknown> = {}) =>
  mount(SectionNav, { props: { label: 'Knowledge Base', sections: SECTIONS, ...props }, slots: slots as never })

describe('SectionNav', () => {
  it('renders a labelled nav with section headings and items in order', () => {
    const w = render({ title: 'Knowledge Base' })
    expect(w.find('nav').attributes('aria-label')).toBe('Knowledge Base')
    expect(w.find('h2').text()).toBe('Knowledge Base')
    expect(w.findAll('.aui-section-nav__sect').map((n) => n.text())).toEqual(['Browse', 'Research'])
    expect(w.findAll('a').map((a) => a.text())).toEqual(['Browser', 'Graph', 'Web'])
  })

  it('marks only the active item with aria-current="page"', () => {
    const links = render().findAll('a')
    expect(links[0].attributes('aria-current')).toBe('page')
    expect(links[1].attributes('aria-current')).toBeUndefined()
  })

  it('puts adv and the per-item class on the link, and adv on the section label', () => {
    const w = render()
    const graph = w.findAll('a')[1]
    expect(graph.classes()).toEqual(expect.arrayContaining(['adv', 'extra']))
    expect(w.findAll('.aui-section-nav__sect')[1].classes()).toContain('adv')
    expect(w.findAll('a')[0].classes()).not.toContain('adv')
  })

  it('binds the target as href for a plain anchor and as `to` for a link component', () => {
    expect(render().find('a').attributes('href')).toBe('/browser')
    const Link = defineComponent({
      props: { to: { type: String, required: true } },
      setup: (p, { slots }) => () => h('a', { 'data-to': p.to }, slots.default?.()),
    })
    expect(render({ linkAs: Link }).find('a').attributes('data-to')).toBe('/browser')
  })

  it('renders the icon, trailing and footer slots', () => {
    const w = render({}, {
      icon: '<i class="ico" />',
      trailing: '<b class="cnt">2</b>',
      footer: '<span class="foot">note</span>',
    })
    expect(w.findAll('.ico')).toHaveLength(3)
    expect(w.findAll('.cnt')).toHaveLength(3)
    expect(w.find('.foot').text()).toBe('note')
  })

  it('makes a disabled item inert for keyboard focus', () => {
    const w = render({ sections: [{ id: 's', items: [{ id: 'a', label: 'A', to: '/a', disabled: true }] }] })
    expect(w.find('a').attributes('aria-disabled')).toBe('true')
    expect(w.find('a').attributes('tabindex')).toBe('-1')
  })
})
