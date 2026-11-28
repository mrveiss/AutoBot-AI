// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BaseCard behavioral tests (#14786 batch 1). Covers the optional
// header/footer slots, the default body slot, and the `flush` prop — 3
// consumers across both apps depend on this contract.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import cardSource from '../BaseCard.vue?raw'
import BaseCard from '../BaseCard.vue'

describe('BaseCard', () => {
  it('renders the default slot inside .aui-card__body', () => {
    // fails if the default <slot /> is removed from .aui-card__body
    const wrapper = mount(BaseCard, { slots: { default: 'Body content' } })
    expect(wrapper.find('.aui-card__body').text()).toBe('Body content')
  })

  it('omits the header element when no header slot is provided', () => {
    // fails if `v-if="$slots.header"` is dropped (header would always render,
    // even as an empty element, when the caller passes no header content)
    const wrapper = mount(BaseCard, { slots: { default: 'Body' } })
    expect(wrapper.find('.aui-card__header').exists()).toBe(false)
  })

  it('renders the header element and its slot content when provided', () => {
    // fails if the #header slot stops being projected into .aui-card__header
    const wrapper = mount(BaseCard, {
      slots: { header: '<h2>Card title</h2>', default: 'Body' },
    })
    const header = wrapper.find('.aui-card__header')
    expect(header.exists()).toBe(true)
    expect(header.text()).toBe('Card title')
  })

  it('omits the footer element when no footer slot is provided', () => {
    // fails if `v-if="$slots.footer"` is dropped
    const wrapper = mount(BaseCard, { slots: { default: 'Body' } })
    expect(wrapper.find('.aui-card__footer').exists()).toBe(false)
  })

  it('renders the footer element and its slot content when provided', () => {
    // fails if the #footer slot stops being projected into .aui-card__footer
    const wrapper = mount(BaseCard, {
      slots: { default: 'Body', footer: '<button>Confirm</button>' },
    })
    const footer = wrapper.find('.aui-card__footer')
    expect(footer.exists()).toBe(true)
    expect(footer.text()).toBe('Confirm')
  })

  it('does not apply aui-card__body--flush by default', () => {
    // fails if the `flush` prop's withDefaults() default value changes from false
    const wrapper = mount(BaseCard, { slots: { default: 'Body' } })
    expect(wrapper.find('.aui-card__body').classes()).not.toContain('aui-card__body--flush')
  })

  it('applies aui-card__body--flush when flush=true', () => {
    // fails if the `flush` prop stops driving the aui-card__body--flush class
    const wrapper = mount(BaseCard, { props: { flush: true }, slots: { default: 'Body' } })
    expect(wrapper.find('.aui-card__body').classes()).toContain('aui-card__body--flush')
  })

  it('defaults to the original kit card: variant=default, size=md, no scroll', () => {
    // fails if a default changes -- the SLM's existing kit cards rely on the original look
    const wrapper = mount(BaseCard, { slots: { default: 'x' } })
    expect(wrapper.classes()).toEqual(expect.arrayContaining(['aui-card', 'aui-card--default', 'aui-card--md']))
    expect(wrapper.find('.aui-card__body').classes()).not.toContain('aui-card__body--scroll')
  })

  it.each(['default', 'bordered', 'elevated', 'flat', 'dark'] as const)('applies the %s frame', (variant) => {
    expect(mount(BaseCard, { props: { variant } }).classes()).toContain(`aui-card--${variant}`)
  })

  it.each(['sm', 'md', 'lg'] as const)('applies the %s text scale', (size) => {
    expect(mount(BaseCard, { props: { size } }).classes()).toContain(`aui-card--${size}`)
  })

  it('renders a title and subtitle header without a header slot', () => {
    const wrapper = mount(BaseCard, { props: { title: 'Panel', subtitle: 'Sub' } })
    expect(wrapper.get('.aui-card__title').text()).toBe('Panel')
    expect(wrapper.get('.aui-card__subtitle').text()).toBe('Sub')
  })

  it('a header slot replaces the title block, and actions sit beside it', () => {
    const wrapper = mount(BaseCard, {
      props: { title: 'Ignored' },
      slots: { header: '<span data-testid="h">Custom</span>', actions: '<button>Go</button>' },
    })
    expect(wrapper.find('.aui-card__title').exists()).toBe(false)
    expect(wrapper.get('[data-testid="h"]').text()).toBe('Custom')
    expect(wrapper.get('.aui-card__actions button').text()).toBe('Go')
  })

  it('shows the header for actions alone, with no title', () => {
    const wrapper = mount(BaseCard, { slots: { actions: '<button>Go</button>' } })
    expect(wrapper.find('.aui-card__header').exists()).toBe(true)
    expect(wrapper.find('.aui-card__title').exists()).toBe(false)
  })

  it('scrollable makes the body scroll', () => {
    const wrapper = mount(BaseCard, { props: { scrollable: true } })
    expect(wrapper.get('.aui-card__body').classes()).toContain('aui-card__body--scroll')
  })

  it('no frame adds a shadow: the design system draws none (#18691)', () => {
    // jsdom does not apply SFC <style>, so the rules are read from the source. The base
    // card's pre-existing shadow is #18691's to remove; a variant must not add another.
    const css = cardSource.split('<style scoped>')[1]
    const shadows = [...css.matchAll(/box-shadow:\s*([^;]+);/g)].map((m) => m[1].trim())
    expect(shadows.filter((s) => s !== 'none')).toEqual(['var(--aui-shadow-sm)'])
  })
})
