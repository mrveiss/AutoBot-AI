// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BaseBadge behavioral tests (#14786 batch 1). Covers every SemanticVariant
// and BadgeSize the component's own type unions expose, plus slot content
// and the default props — 7 consumers of BaseBadge across both apps depend
// on this class-mapping contract.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import badgeSource from '../BaseBadge.vue?raw'
import BaseBadge, { type BadgeVariant, type BadgeSize, type BadgeTone } from '../BaseBadge.vue'

const VARIANTS: BadgeVariant[] = ['neutral', 'primary', 'success', 'warning', 'error', 'info']
const SIZES: BadgeSize[] = ['xs', 'sm', 'md', 'lg']
const TONES: BadgeTone[] = ['solid', 'subtle', 'outline']

describe('BaseBadge', () => {
  it('renders default slot content', () => {
    // fails if the <slot /> in the template is removed or the tag stops rendering children
    const wrapper = mount(BaseBadge, { slots: { default: 'Active' } })
    expect(wrapper.text()).toBe('Active')
  })

  it('defaults to variant=neutral, size=md, tone=subtle, rounded, not removable', () => {
    // fails if a default changes -- subtle is the design system's default badge (#18691); solid users say so
    const wrapper = mount(BaseBadge)
    expect(wrapper.classes()).toEqual(expect.arrayContaining(['aui-badge--neutral', 'aui-badge--md', 'aui-badge--subtle']))
    expect(wrapper.classes()).not.toContain('aui-badge--square')
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it.each(TONES)('applies the aui-badge--%s class for tone=%s', (tone) => {
    const wrapper = mount(BaseBadge, { props: { tone } })
    expect(wrapper.classes()).toContain(`aui-badge--${tone}`)
  })

  it('renders the label prop when no default slot is given, and the slot over it', () => {
    expect(mount(BaseBadge, { props: { label: 'From prop' } }).text()).toBe('From prop')
    expect(mount(BaseBadge, { props: { label: 'From prop' }, slots: { default: 'From slot' } }).text()).toBe('From slot')
  })

  it('renders an icon slot before the text', () => {
    const wrapper = mount(BaseBadge, { props: { label: 'x' }, slots: { icon: '<i data-testid="icon" />' } })
    expect(wrapper.element.firstElementChild?.getAttribute('data-testid')).toBe('icon')
    expect(wrapper.text()).toBe('x')
  })

  it('square and monospace are classes, off by default', () => {
    const wrapper = mount(BaseBadge, { props: { rounded: false, monospace: true } })
    expect(wrapper.classes()).toEqual(expect.arrayContaining(['aui-badge--square', 'aui-badge--mono']))
  })

  it('a removable badge has a named remove button that emits remove and stops the click', async () => {
    const outer = { clicked: 0 }
    const wrapper = mount(
      { components: { BaseBadge }, template: '<div @click="clicked++"><BaseBadge removable remove-label="Remove tag" label="Tag" @remove="removed++" /></div>',
        data: () => ({ clicked: 0, removed: 0 }) },
    )
    const button = wrapper.get('button')
    expect(button.attributes('aria-label')).toBe('Remove tag')
    expect(button.attributes('type')).toBe('button')
    await button.trigger('click')
    expect((wrapper.vm as unknown as { removed: number }).removed).toBe(1)
    expect((wrapper.vm as unknown as { clicked: number }).clicked).toBe(outer.clicked)
  })

  it.each(VARIANTS)('applies the aui-badge--%s class for variant=%s', (variant) => {
    // fails if a variant stops mapping to its own aui-badge--{variant} class
    const wrapper = mount(BaseBadge, { props: { variant } })
    expect(wrapper.classes()).toContain(`aui-badge--${variant}`)
  })

  it.each(SIZES)('applies the aui-badge--%s class for size=%s', (size) => {
    // fails if a size stops mapping to its own aui-badge--{size} class
    const wrapper = mount(BaseBadge, { props: { size } })
    expect(wrapper.classes()).toContain(`aui-badge--${size}`)
  })

  it('recomputes the variant class reactively when the prop changes', async () => {
    // fails if the class list is ever computed once at mount time instead of
    // reactively off the `variant` prop (e.g. hardcoded into a non-reactive const)
    const wrapper = mount(BaseBadge, { props: { variant: 'success' } })
    expect(wrapper.classes()).toContain('aui-badge--success')
    await wrapper.setProps({ variant: 'error' })
    expect(wrapper.classes()).toContain('aui-badge--error')
    expect(wrapper.classes()).not.toContain('aui-badge--success')
  })

  it('always carries the base aui-badge class regardless of variant/size', () => {
    // fails if the static 'aui-badge' base class is dropped from the class array
    const wrapper = mount(BaseBadge, { props: { variant: 'info', size: 'sm' } })
    expect(wrapper.classes()).toContain('aui-badge')
  })

  it('the base and solid rules declare no border, so existing solid badges keep their size', () => {
    // jsdom does not apply SFC <style>, so the rules are read from the source: a border on
    // .aui-badge or .aui-badge--solid would grow every existing kit badge by 2px (#14776 review).
    const css = badgeSource.split('<style scoped>')[1]
    const rule = (selector: string) => css.match(new RegExp(`(?:^|\\n)${selector.replace(/[.*+?^${}()|[\]\\-]/g, '\\$&')} \\{([^}]*)\\}`))?.[1] ?? ''
    expect(rule('.aui-badge')).toContain('display: inline-flex')
    expect(rule('.aui-badge')).not.toMatch(/\bborder\s*:/)
    expect(rule('.aui-badge--solid')).not.toMatch(/\bborder/)
    expect(css).toMatch(/\.aui-badge--subtle,\s*\.aui-badge--outline \{\s*border: 1px solid transparent;/)
  })
})
