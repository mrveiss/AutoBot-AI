// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// SkipLink behavioral tests (#17565). The contract both apps rely on:
// activating the link moves FOCUS to the target landmark, not only scroll.

import { describe, it, expect, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import SkipLink from '../SkipLink.vue'

describe('SkipLink', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('renders the caller-supplied label and links to the target', () => {
    const wrapper = mount(SkipLink, { props: { label: 'Skip it', target: '#content' } })
    expect(wrapper.text()).toBe('Skip it')
    expect(wrapper.attributes('href')).toBe('#content')
  })

  it('targets #main-content by default', () => {
    const wrapper = mount(SkipLink, { props: { label: 'Skip' } })
    expect(wrapper.attributes('href')).toBe('#main-content')
  })

  it('moves focus to a non-focusable landmark when activated', async () => {
    // fails if the handler only scrolls, or drops the tabindex that lets a
    // <main> take programmatic focus
    document.body.innerHTML = '<main id="main-content">content</main>'
    const main = document.getElementById('main-content') as HTMLElement
    const wrapper = mount(SkipLink, { props: { label: 'Skip' }, attachTo: document.body })

    await wrapper.trigger('click')

    expect(document.activeElement).toBe(main)
    expect(main.getAttribute('tabindex')).toBe('-1')
    wrapper.unmount()
  })

  it('keeps an existing tabindex on the target', async () => {
    document.body.innerHTML = '<nav id="navigation" tabindex="0">nav</nav>'
    const nav = document.getElementById('navigation') as HTMLElement
    const wrapper = mount(SkipLink, { props: { label: 'Skip', target: '#navigation' }, attachTo: document.body })

    await wrapper.trigger('click')

    expect(document.activeElement).toBe(nav)
    expect(nav.getAttribute('tabindex')).toBe('0')
    wrapper.unmount()
  })

  it('leaves the browser hash jump alone when the target does not exist', async () => {
    // fails if the handler calls preventDefault (or throws) with no target to focus
    const wrapper = mount(SkipLink, { props: { label: 'Skip', target: '#absent' }, attachTo: document.body })
    const event = new MouseEvent('click', { bubbles: true, cancelable: true })

    wrapper.element.dispatchEvent(event)

    expect(event.defaultPrevented).toBe(false)
    wrapper.unmount()
  })
})
