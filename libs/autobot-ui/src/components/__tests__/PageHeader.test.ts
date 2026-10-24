// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// PageHeader (#17563): a header landmark whose title is a real heading at the caller's level,
// with optional subtitle, breadcrumb, leading, actions and toolbar regions that render only
// when supplied.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PageHeader from '../PageHeader.vue'

describe('PageHeader', () => {
  it('renders the title as an h1 by default, and nothing it was not given', () => {
    const w = mount(PageHeader, { props: { title: 'Analytics' } })
    expect(w.element.tagName).toBe('HEADER')
    expect(w.find('h1').text()).toBe('Analytics')
    expect(w.find('.aui-page-header__subtitle').exists()).toBe(false)
    expect(w.find('.aui-page-header__actions').exists()).toBe(false)
    expect(w.find('.aui-page-header__breadcrumb').exists()).toBe(false)
    expect(w.find('.aui-page-header__toolbar').exists()).toBe(false)
  })

  it('uses the given heading level', () => {
    const w = mount(PageHeader, { props: { title: 'Files', level: 2 } })
    expect(w.find('h2').text()).toBe('Files')
    expect(w.find('h1').exists()).toBe(false)
  })

  it('shows the subtitle and the slotted regions', () => {
    const w = mount(PageHeader, {
      props: { title: 'Chat', subtitle: '12 messages' },
      slots: {
        breadcrumb: '<nav>trail</nav>',
        leading: '<button>menu</button>',
        actions: '<button>export</button>',
        default: '<input />',
      },
    })
    expect(w.find('.aui-page-header__subtitle').text()).toBe('12 messages')
    expect(w.find('.aui-page-header__breadcrumb nav').exists()).toBe(true)
    expect(w.find('.aui-page-header__start button').text()).toBe('menu')
    expect(w.find('.aui-page-header__actions button').text()).toBe('export')
    expect(w.find('.aui-page-header__toolbar input').exists()).toBe(true)
  })

  it('takes rich title content from the title slot', () => {
    const w = mount(PageHeader, { slots: { title: '<span class="icon"></span>Analytics' } })
    expect(w.find('h1 .icon').exists()).toBe(true)
    expect(w.find('h1').text()).toBe('Analytics')
  })

  it('renders a toolbar-only header without an empty heading', () => {
    const w = mount(PageHeader, { slots: { default: '<input />' } })
    expect(w.find('h1').exists()).toBe(false)
    expect(w.find('.aui-page-header__row').exists()).toBe(false)
    expect(w.find('.aui-page-header__toolbar input').exists()).toBe(true)
  })
})
