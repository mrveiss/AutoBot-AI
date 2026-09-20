// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BaseButton behavioral tests (#14786 batch 1). Covers every ButtonVariant
// and ButtonSize the component's own type unions expose, the disabled/loading
// interplay, the type/block/aria-busy attrs, and slot content — 24 consumers
// across both apps depend on this contract.

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import BaseButton, { type ButtonVariant, type ButtonSize } from '../BaseButton.vue'

const VARIANTS: ButtonVariant[] = ['primary', 'secondary', 'ghost', 'danger']
const SIZES: ButtonSize[] = ['sm', 'md', 'lg']

describe('BaseButton', () => {
  it('renders a real <button> with default slot content', () => {
    // fails if the template stops rendering a native <button> element or the
    // default slot is no longer projected into .aui-btn__label
    const wrapper = mount(BaseButton, { slots: { default: 'Save' } })
    expect(wrapper.element.tagName).toBe('BUTTON')
    expect(wrapper.find('.aui-btn__label').text()).toBe('Save')
  })

  it('defaults to variant=primary, size=md, type=button, not disabled/loading/block', () => {
    // fails if any withDefaults() default value on BaseButton changes silently
    const wrapper = mount(BaseButton)
    expect(wrapper.classes()).toContain('aui-btn--primary')
    expect(wrapper.classes()).toContain('aui-btn--md')
    expect(wrapper.attributes('type')).toBe('button')
    expect(wrapper.attributes('disabled')).toBeUndefined()
    expect(wrapper.classes()).not.toContain('aui-btn--block')
    expect(wrapper.classes()).not.toContain('aui-btn--loading')
  })

  it.each(VARIANTS)('applies the aui-btn--%s class for variant=%s', (variant) => {
    // fails if a variant stops mapping to its own aui-btn--{variant} class
    const wrapper = mount(BaseButton, { props: { variant } })
    expect(wrapper.classes()).toContain(`aui-btn--${variant}`)
  })

  it.each(SIZES)('applies the aui-btn--%s class for size=%s', (size) => {
    // fails if a size stops mapping to its own aui-btn--{size} class
    const wrapper = mount(BaseButton, { props: { size } })
    expect(wrapper.classes()).toContain(`aui-btn--${size}`)
  })

  it.each(['button', 'submit', 'reset'] as const)('forwards type=%s to the native type attribute', (type) => {
    // fails if the `:type="type"` binding is removed or hardcoded to "button"
    const wrapper = mount(BaseButton, { props: { type } })
    expect(wrapper.attributes('type')).toBe(type)
  })

  it('applies the disabled attribute when disabled=true', () => {
    // fails if `:disabled="isDisabled"` stops reading the `disabled` prop
    const wrapper = mount(BaseButton, { props: { disabled: true } })
    expect(wrapper.attributes('disabled')).toBeDefined()
  })

  it('applies the disabled attribute when loading=true even if disabled=false', () => {
    // fails if isDisabled stops being `disabled || loading` (e.g. reverts to
    // reading only the `disabled` prop, letting a loading button stay clickable)
    const wrapper = mount(BaseButton, { props: { disabled: false, loading: true } })
    expect(wrapper.attributes('disabled')).toBeDefined()
  })

  it('sets aria-busy="true" when loading and omits the attribute when not', () => {
    // fails if `:aria-busy="loading || undefined"` stops omitting the attribute
    // for false (e.g. renders aria-busy="false" instead of dropping it)
    const loading = mount(BaseButton, { props: { loading: true } })
    expect(loading.attributes('aria-busy')).toBe('true')

    const notLoading = mount(BaseButton, { props: { loading: false } })
    expect(notLoading.attributes('aria-busy')).toBeUndefined()
  })

  it('renders the spinner element only while loading', () => {
    // fails if `v-if="loading"` on .aui-btn__spinner is removed (spinner
    // would render unconditionally or never render at all)
    const loading = mount(BaseButton, { props: { loading: true } })
    expect(loading.find('.aui-btn__spinner').exists()).toBe(true)

    const notLoading = mount(BaseButton, { props: { loading: false } })
    expect(notLoading.find('.aui-btn__spinner').exists()).toBe(false)
  })

  it('applies aui-btn--block only when block=true', () => {
    // fails if the block prop stops driving the aui-btn--block class
    const wrapper = mount(BaseButton, { props: { block: true } })
    expect(wrapper.classes()).toContain('aui-btn--block')
  })

  it('applies aui-btn--loading only when loading=true', () => {
    // fails if the loading prop stops driving the aui-btn--loading class
    const wrapper = mount(BaseButton, { props: { loading: true } })
    expect(wrapper.classes()).toContain('aui-btn--loading')
  })

  it('forwards a parent @click listener straight onto the native button (no declared emits)', async () => {
    // BaseButton declares no defineEmits(), so a parent's @click reaches the
    // button purely via Vue's attrs-fallthrough onto the single root element.
    // fails if the root element stops being the <button> that receives
    // fallthrough attrs (e.g. an extra wrapper element, or inheritAttrs:
    // false without manually re-forwarding attrs onto the button)
    const onClick = vi.fn()
    const wrapper = mount(BaseButton, { attrs: { onClick } })
    await wrapper.trigger('click')
    expect(onClick).toHaveBeenCalledTimes(1)
  })
})
