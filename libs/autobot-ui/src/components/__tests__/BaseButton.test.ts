// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BaseButton behavioral tests (#14786 batch 1). Covers every ButtonVariant
// and ButtonSize the component's own type unions expose, the disabled/loading
// interplay, the type/block/aria-busy attrs, and slot content — every consumer
// in both apps (the main app's local fork was retired into it, #18849) depend on this contract.

import { describe, it, expect, vi } from 'vitest'
import { h } from 'vue'
import { mount } from '@vue/test-utils'
import buttonSource from '../BaseButton.vue?raw'
import BaseButton, { type ButtonVariant, type ButtonSize } from '../BaseButton.vue'

const VARIANTS: ButtonVariant[] = [
  'primary', 'secondary', 'ghost', 'error', 'success', 'warning', 'info', 'outline', 'link',
]
const SIZES: ButtonSize[] = ['xs', 'sm', 'md', 'lg', 'xl']

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

  it('renders the icon-left slot before the label', () => {
    // fails if the icon-left slot is dropped or rendered after the label
    const wrapper = mount(BaseButton, {
      slots: { default: 'Add', 'icon-left': '<i data-testid="icon" />' },
    })
    expect(wrapper.element.firstElementChild?.getAttribute('data-testid')).toBe('icon')
    expect(wrapper.text()).toBe('Add')
  })

  it('hides the icon-left slot while loading, showing the spinner instead', () => {
    // fails if the icon renders beside the spinner (main-button behaviour: icons hidden while loading)
    const wrapper = mount(BaseButton, {
      props: { loading: true },
      slots: { default: 'Save', 'icon-left': '<i data-testid="icon" />' },
    })
    expect(wrapper.find('[data-testid="icon"]').exists()).toBe(false)
    expect(wrapper.find('.aui-btn__spinner').exists()).toBe(true)
  })

  it('does not fire click on a disabled or loading button', async () => {
    // fails if a loading/disabled button can still trigger the parent's handler
    const onClick = vi.fn()
    await mount(BaseButton, { props: { disabled: true }, attrs: { onClick } }).trigger('click')
    await mount(BaseButton, { props: { loading: true }, attrs: { onClick } }).trigger('click')
    expect(onClick).not.toHaveBeenCalled()
  })

  it('passes aria-label through to the native button', () => {
    // fails if attrs stop falling through to the root (icon-only buttons would lose their name)
    const wrapper = mount(BaseButton, { attrs: { 'aria-label': 'Close' } })
    expect(wrapper.attributes('aria-label')).toBe('Close')
  })

  it('renders as a link through `as`, passing href and omitting button-only attrs', () => {
    // fails if `as` stops choosing the element, or type/disabled leak onto a link
    const wrapper = mount(BaseButton, {
      props: { as: 'a' },
      attrs: { href: '/docs' },
      slots: { default: 'Docs' },
    })
    expect(wrapper.element.tagName).toBe('A')
    expect(wrapper.attributes('href')).toBe('/docs')
    expect(wrapper.attributes('type')).toBeUndefined()
    expect(wrapper.attributes('disabled')).toBeUndefined()
  })

  it('renders a component passed as `as` and forwards `to` (router-link without a router import)', () => {
    // fails if the kit stops accepting a component, which is how callers supply RouterLink
    const Link = { props: ['to'], template: '<a :href="to"><slot /></a>' }
    const wrapper = mount(BaseButton, { props: { as: Link }, attrs: { to: '/x' }, slots: { default: 'Go' } })
    expect(wrapper.attributes('href')).toBe('/x')
    expect(wrapper.classes()).toContain('aui-btn--primary')
  })

  it('marks a disabled link aria-disabled instead of using the disabled attribute', () => {
    // fails if a non-button element receives `disabled` or loses its disabled semantics
    const wrapper = mount(BaseButton, { props: { as: 'a', disabled: true } })
    expect(wrapper.attributes('aria-disabled')).toBe('true')
    expect(wrapper.attributes('disabled')).toBeUndefined()
  })

  it.each([
    ['disabled', { disabled: true }],
    ['loading', { loading: true }],
  ])('makes a %s link inert: no navigation, no caller click, out of the tab order', (_, state) => {
    // fails if a disabled/loading `as="a"` still navigates, runs its @click, or takes focus
    const onClick = vi.fn()
    const wrapper = mount(BaseButton, { props: { as: 'a', ...state }, attrs: { href: '#x', onClick } })
    const event = new MouseEvent('click', { bubbles: true, cancelable: true })
    wrapper.element.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
    expect(onClick).not.toHaveBeenCalled()
    expect(wrapper.attributes('tabindex')).toBe('-1')
  })

  it('blocks a disabled RouterLink-like component whose own root click handler navigates', () => {
    // fails if the inert guard runs after the component's own handler (RouterLink's navigate)
    const navigate = vi.fn((e: MouseEvent) => e.preventDefault())
    const RouterLinkLike = { props: ['to'], setup: (p: { to: string }, { slots }: { slots: Record<string, () => unknown> }) => () => h('a', { href: p.to, onClick: navigate }, slots.default?.()) }
    const disabled = mount(BaseButton, { props: { as: RouterLinkLike, disabled: true }, attrs: { to: '/x' } })
    disabled.element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
    expect(navigate).not.toHaveBeenCalled()
    const enabled = mount(BaseButton, { props: { as: RouterLinkLike }, attrs: { to: '/x' } })
    enabled.element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
    expect(navigate).toHaveBeenCalledOnce()
  })

  it('leaves an enabled link alone: it navigates, runs its @click and keeps its tab stop', () => {
    // contrast case: fails if the inert guard fires when the link is enabled
    const onClick = vi.fn()
    const wrapper = mount(BaseButton, { props: { as: 'a' }, attrs: { href: '#x', onClick } })
    const event = new MouseEvent('click', { bubbles: true, cancelable: true })
    wrapper.element.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(false)
    expect(onClick).toHaveBeenCalledOnce()
    expect(wrapper.attributes('tabindex')).toBeUndefined()
  })

  it('never shows a hover or active state on an aria-disabled element', () => {
    // fails if a `:hover:not(:disabled)` rule can still match a disabled link
    const states = buttonSource.match(/:(hover|active):not\(:disabled\)[^{,]*/g) ?? []
    expect(states.length).toBeGreaterThan(0)
    expect(states.every((s) => s.includes(":not([aria-disabled='true'])"))).toBe(true)
  })

  it('styles through kit tokens only: no literal colour or box-shadow in the source', () => {
    // fails if a raw palette value or a shadow enters the component (design system: tokens, no shadows)
    expect(buttonSource).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(|box-shadow/)
  })
})
