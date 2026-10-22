// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BaseSwitch (#14780): a named switch button; click, Space and Enter toggle it; disabled
// does nothing; v-model and change carry the new value.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import BaseSwitch from '../BaseSwitch.vue'

function render(props: Record<string, unknown> = {}) {
  return mount(BaseSwitch, { props: { modelValue: false, label: 'Dark mode', ...props }, attachTo: document.body })
}

describe('BaseSwitch', () => {
  it('is a button with role switch, named by label, reporting its state', () => {
    const w = render({ modelValue: true })
    const b = w.find('button')
    expect(b.attributes('type')).toBe('button')
    expect(b.attributes('role')).toBe('switch')
    expect(b.attributes('aria-label')).toBe('Dark mode')
    expect(b.attributes('aria-checked')).toBe('true')
    expect(b.classes()).toContain('aui-switch--on')
    w.unmount()
  })

  it('a click emits the opposite value through v-model and change', async () => {
    const w = render({ modelValue: false })
    await w.find('button').trigger('click')
    expect(w.emitted('update:modelValue')).toEqual([[true]])
    expect(w.emitted('change')).toEqual([[true]])
    w.unmount()
  })

  it('reports off as aria-checked="false"', () => {
    const w = render({ modelValue: false })
    expect(w.find('button').attributes('aria-checked')).toBe('false')
    w.unmount()
  })

  it('is keyboard operable: a native button, in the tab order, no tabindex override', () => {
    // Space and Enter activate a native <button> (fire click) in every browser; jsdom does not
    // synthesise that, so the contract asserted is "a real, focusable button", not key events.
    const w = render()
    const b = w.find('button').element as HTMLButtonElement
    b.focus()
    expect(document.activeElement).toBe(b)
    expect(b.hasAttribute('tabindex')).toBe(false)
    w.unmount()
  })

  it('disabled: not clickable, nothing emitted', async () => {
    const w = render({ disabled: true })
    expect(w.find('button').attributes('disabled')).toBeDefined()
    await w.find('button').trigger('click')
    expect(w.emitted('update:modelValue')).toBeUndefined()
    w.unmount()
  })

  it('applies the size class', () => {
    expect(render({ size: 'sm' }).find('button').classes()).toContain('aui-switch--sm')
    expect(render().find('button').classes()).toContain('aui-switch--md')
  })
})
