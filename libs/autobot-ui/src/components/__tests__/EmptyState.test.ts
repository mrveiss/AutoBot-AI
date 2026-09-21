// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// EmptyState behavioral tests (#14786 batch 1). Covers the title/description
// prop-vs-slot fallback, the icon/actions slots, and role="status" — 10
// consumers across both apps depend on this contract.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import EmptyState from '../EmptyState.vue'

describe('EmptyState', () => {
  it('renders role="status" on the root element', () => {
    // fails if role="status" is removed from the root <div>
    const wrapper = mount(EmptyState)
    expect(wrapper.attributes('role')).toBe('status')
  })

  it('renders nothing for title/description/icon/actions when none are given', () => {
    // fails if any of the four `v-if="$slots.x || x"` guards stop gating
    // their element, causing an empty title/description/icon/actions block
    // to render even when the caller supplied nothing
    const wrapper = mount(EmptyState)
    expect(wrapper.find('.aui-empty__title').exists()).toBe(false)
    expect(wrapper.find('.aui-empty__description').exists()).toBe(false)
    expect(wrapper.find('.aui-empty__icon').exists()).toBe(false)
    expect(wrapper.find('.aui-empty__actions').exists()).toBe(false)
  })

  it('renders the title prop via the #title slot fallback', () => {
    // fails if `<slot name="title">{{ title }}</slot>` stops falling back to
    // the prop when no #title slot is passed
    const wrapper = mount(EmptyState, { props: { title: 'No results' } })
    expect(wrapper.find('.aui-empty__title').text()).toBe('No results')
  })

  it('lets the #title slot override the title prop', () => {
    // fails if the slot fallback is replaced with unconditional prop
    // rendering, i.e. the slot content stops taking priority over the prop
    const wrapper = mount(EmptyState, {
      props: { title: 'Prop title' },
      slots: { title: '<strong>Slot title</strong>' },
    })
    const title = wrapper.find('.aui-empty__title')
    expect(title.text()).toBe('Slot title')
    expect(title.text()).not.toContain('Prop title')
  })

  it('renders the description prop via the #description slot fallback', () => {
    // fails if `<slot name="description">{{ description }}</slot>` stops
    // falling back to the prop when no #description slot is passed
    const wrapper = mount(EmptyState, { props: { description: 'Try a different filter' } })
    expect(wrapper.find('.aui-empty__description').text()).toBe('Try a different filter')
  })

  it('lets the #description slot override the description prop', () => {
    // fails if the slot fallback is replaced with unconditional prop rendering
    const wrapper = mount(EmptyState, {
      props: { description: 'Prop description' },
      slots: { description: 'Slot description' },
    })
    expect(wrapper.find('.aui-empty__description').text()).toBe('Slot description')
  })

  it('renders the icon slot with aria-hidden="true" when provided', () => {
    // fails if `v-if="$slots.icon"` is dropped, or aria-hidden stops being
    // applied to the icon wrapper (decorative icon would become announced)
    const wrapper = mount(EmptyState, { slots: { icon: '<svg data-testid="icon" />' } })
    const icon = wrapper.find('.aui-empty__icon')
    expect(icon.exists()).toBe(true)
    expect(icon.attributes('aria-hidden')).toBe('true')
    expect(icon.find('[data-testid="icon"]').exists()).toBe(true)
  })

  it('renders the actions slot only when provided', () => {
    // fails if `v-if="$slots.actions"` is dropped
    const wrapper = mount(EmptyState, {
      slots: { actions: '<button>Retry</button>' },
    })
    const actions = wrapper.find('.aui-empty__actions')
    expect(actions.exists()).toBe(true)
    expect(actions.text()).toBe('Retry')
  })
})
