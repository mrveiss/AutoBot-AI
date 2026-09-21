// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BaseBadge behavioral tests (#14786 batch 1). Covers every SemanticVariant
// and BadgeSize the component's own type unions expose, plus slot content
// and the default props — 7 consumers of BaseBadge across both apps depend
// on this class-mapping contract.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import BaseBadge, { type BadgeVariant, type BadgeSize } from '../BaseBadge.vue'

const VARIANTS: BadgeVariant[] = ['neutral', 'primary', 'success', 'warning', 'danger', 'info']
const SIZES: BadgeSize[] = ['sm', 'md']

describe('BaseBadge', () => {
  it('renders default slot content', () => {
    // fails if the <slot /> in the template is removed or the tag stops rendering children
    const wrapper = mount(BaseBadge, { slots: { default: 'Active' } })
    expect(wrapper.text()).toBe('Active')
  })

  it('defaults to variant=neutral and size=md', () => {
    // fails if the withDefaults() default values for variant/size are changed or dropped
    const wrapper = mount(BaseBadge)
    expect(wrapper.classes()).toContain('aui-badge--neutral')
    expect(wrapper.classes()).toContain('aui-badge--md')
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
    await wrapper.setProps({ variant: 'danger' })
    expect(wrapper.classes()).toContain('aui-badge--danger')
    expect(wrapper.classes()).not.toContain('aui-badge--success')
  })

  it('always carries the base aui-badge class regardless of variant/size', () => {
    // fails if the static 'aui-badge' base class is dropped from the class array
    const wrapper = mount(BaseBadge, { props: { variant: 'info', size: 'sm' } })
    expect(wrapper.classes()).toContain('aui-badge')
  })
})
