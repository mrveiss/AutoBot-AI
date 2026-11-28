// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BaseSpinner and BaseSkeleton contract tests (#19906).

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import BaseSpinner from '../BaseSpinner.vue'
import BaseSkeleton from '../BaseSkeleton.vue'

describe('BaseSpinner', () => {
  it('is hidden from assistive tech when it has no label', () => {
    const wrapper = mount(BaseSpinner)
    expect(wrapper.attributes('aria-hidden')).toBe('true')
    expect(wrapper.attributes('role')).toBeUndefined()
  })

  it('announces a passed label as a status', () => {
    const wrapper = mount(BaseSpinner, { props: { label: 'Loading rows', size: 'lg' } })
    expect(wrapper.attributes('role')).toBe('status')
    expect(wrapper.find('.aui-spinner__label').text()).toBe('Loading rows')
    expect(wrapper.classes()).toContain('aui-spinner--lg')
  })
})

describe('BaseSkeleton', () => {
  it('renders one decorative bar by default', () => {
    const wrapper = mount(BaseSkeleton)
    expect(wrapper.attributes('aria-hidden')).toBe('true')
    expect(wrapper.findAll('.aui-skeleton')).toHaveLength(1)
  })

  it('stacks lines and shortens the last one', () => {
    const wrapper = mount(BaseSkeleton, { props: { lines: 3, width: '100%' } })
    const bars = wrapper.findAll('.aui-skeleton')
    expect(bars).toHaveLength(3)
    expect((bars[0].element as HTMLElement).style.width).toBe('100%')
    expect((bars[2].element as HTMLElement).style.width).toBe('60%')
  })

  it('applies the shape class', () => {
    expect(mount(BaseSkeleton, { props: { shape: 'circle' } }).find('.aui-skeleton--circle').exists()).toBe(true)
  })
})
