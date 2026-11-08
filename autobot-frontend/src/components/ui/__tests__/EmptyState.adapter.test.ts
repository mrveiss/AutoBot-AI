// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// The app's EmptyState is an adapter over the kit's (#14776): `message` -> the kit
// `description`, `icon` (an Icon.vue name) -> the kit icon slot, `compact` and the
// `actions` slot pass through. ~48 call sites depend on this prop surface.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import EmptyState from '../EmptyState.vue'

describe('EmptyState adapter', () => {
  it('renders the title and shows message as the kit description', () => {
    // fails if `message` stops being mapped onto the kit's `description`
    const wrapper = mount(EmptyState, { props: { title: 'Nothing here', message: 'Add one to start' } })
    expect(wrapper.find('.aui-empty__title').text()).toBe('Nothing here')
    expect(wrapper.find('.aui-empty__description').text()).toBe('Add one to start')
    expect(wrapper.attributes('role')).toBe('status')
  })

  it('renders no title or description when none are given', () => {
    const wrapper = mount(EmptyState)
    expect(wrapper.find('.aui-empty__title').exists()).toBe(false)
    expect(wrapper.find('.aui-empty__description').exists()).toBe(false)
  })

  it('renders the default inbox icon in the decorative kit icon slot', () => {
    // fails if the `icon` default is dropped or the Icon is not put in the kit icon slot
    const wrapper = mount(EmptyState)
    const slot = wrapper.find('.aui-empty__icon')
    expect(slot.exists()).toBe(true)
    expect(slot.attributes('aria-hidden')).toBe('true')
    expect(slot.find('svg.icon').exists()).toBe(true)
  })

  it('passes a named icon through to Icon', () => {
    const inbox = mount(EmptyState).find('.aui-empty__icon svg path').attributes('d')
    const other = mount(EmptyState, { props: { icon: 'file-import' } }).find('.aui-empty__icon svg path')
    expect(other.exists()).toBe(true)
    expect(other.attributes('d')).not.toBe(inbox)
  })

  it('applies the compact modifier only when compact is set', () => {
    expect(mount(EmptyState).classes()).not.toContain('aui-empty--compact')
    expect(mount(EmptyState, { props: { compact: true } }).classes()).toContain('aui-empty--compact')
  })

  it('renders the actions slot only when provided', () => {
    expect(mount(EmptyState).find('.aui-empty__actions').exists()).toBe(false)
    const wrapper = mount(EmptyState, { slots: { actions: '<button>Retry</button>' } })
    expect(wrapper.find('.aui-empty__actions').text()).toBe('Retry')
  })
})
