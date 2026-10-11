// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BaseTooltip behavioral tests (#18240): a11y wiring and open/close triggers.

import { describe, it, expect, vi, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { h } from 'vue'
import BaseTooltip from '../BaseTooltip.vue'

function make(props: Record<string, unknown> = {}) {
  return mount(BaseTooltip, {
    props: { text: 'Hint', ...props },
    attachTo: document.body,
    slots: {
      default: ({ describedby }: { describedby: string }) =>
        h('button', { type: 'button', 'aria-describedby': describedby }, 'Trigger'),
    },
  })
}

const isOpen = (w: ReturnType<typeof make>) =>
  w.find('[role="tooltip"]').classes().includes('aui-tooltip__bubble--open')

describe('BaseTooltip', () => {
  afterEach(() => {
    vi.useRealTimers()
    document.body.innerHTML = ''
  })

  it('links the trigger to the tooltip with aria-describedby', () => {
    const w = make()
    const tip = w.find('[role="tooltip"]')
    expect(tip.text()).toBe('Hint')
    expect(w.find('button').attributes('aria-describedby')).toBe(tip.attributes('id'))
    w.unmount()
  })

  it('opens on focus immediately and closes on blur', async () => {
    const w = make()
    await w.find('button').trigger('focusin')
    expect(isOpen(w)).toBe(true)
    await w.find('button').trigger('focusout')
    expect(isOpen(w)).toBe(false)
    w.unmount()
  })

  it('closes on Escape', async () => {
    const w = make()
    await w.find('button').trigger('focusin')
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await w.vm.$nextTick()
    expect(isOpen(w)).toBe(false)
    w.unmount()
  })

  it('opens on hover and closes on leave (no delay tokens in jsdom)', async () => {
    const w = make()
    await w.trigger('mouseenter')
    expect(isOpen(w)).toBe(true)
    await w.trigger('mouseleave')
    expect(isOpen(w)).toBe(false)
    w.unmount()
  })

  it('opens on a touch long-press, not on a tap', async () => {
    vi.useFakeTimers()
    const w = make()
    await w.trigger('touchstart')
    await w.trigger('touchend')
    vi.advanceTimersByTime(600)
    await w.vm.$nextTick()
    expect(isOpen(w)).toBe(false)

    await w.trigger('touchstart')
    vi.advanceTimersByTime(600)
    await w.vm.$nextTick()
    expect(isOpen(w)).toBe(true)
    w.unmount()
  })

  it('never opens when disabled', async () => {
    const w = make({ disabled: true })
    await w.find('button').trigger('focusin')
    expect(isOpen(w)).toBe(false)
    w.unmount()
  })
})
