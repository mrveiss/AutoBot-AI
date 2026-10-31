// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BaseAlert behavioral tests (#18819). The one alert for both apps: variant
// class + ARIA semantics, slots, dismiss, dismissLabel, autoDismiss and the
// no-shadow design rule.

import { describe, it, expect, vi, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import alertSource from '../BaseAlert.vue?raw'
import BaseAlert, { type AlertVariant } from '../BaseAlert.vue'

const VARIANTS: AlertVariant[] = ['success', 'info', 'warning', 'error', 'critical']
const ASSERTIVE: AlertVariant[] = ['error', 'critical']

afterEach(() => {
  vi.useRealTimers()
})

describe('BaseAlert', () => {
  it('defaults to variant=info, size=default, status role, icon shown, not dismissible', () => {
    const wrapper = mount(BaseAlert, { props: { message: 'Hi' } })
    expect(wrapper.classes()).toEqual(expect.arrayContaining(['aui-alert--info', 'aui-alert--default']))
    expect(wrapper.classes()).not.toContain('aui-alert--bordered')
    expect(wrapper.attributes('role')).toBe('status')
    expect(wrapper.find('.aui-alert__icon svg').exists()).toBe(true)
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it.each(VARIANTS)('variant=%s gets its class and the right role/aria-live', (variant) => {
    const wrapper = mount(BaseAlert, { props: { variant, message: 'x' } })
    const assertive = ASSERTIVE.includes(variant)
    expect(wrapper.classes()).toContain(`aui-alert--${variant}`)
    expect(wrapper.attributes('role')).toBe(assertive ? 'alert' : 'status')
    expect(wrapper.attributes('aria-live')).toBe(assertive ? 'assertive' : 'polite')
  })

  it('renders message, the default slot over it, and title', () => {
    expect(mount(BaseAlert, { props: { message: 'From prop' } }).text()).toBe('From prop')
    expect(
      mount(BaseAlert, { props: { message: 'From prop' }, slots: { default: 'From slot' } }).text(),
    ).toBe('From slot')
    const titled = mount(BaseAlert, { props: { title: 'Heads up', message: 'm' } })
    expect(titled.find('.aui-alert__title').text()).toBe('Heads up')
  })

  it('suppresses the title prop in compact size but still renders a title slot', () => {
    const compact = mount(BaseAlert, { props: { size: 'compact', title: 'T', message: 'm' } })
    expect(compact.classes()).toContain('aui-alert--compact')
    expect(compact.find('.aui-alert__title').exists()).toBe(false)
    const slotted = mount(BaseAlert, { props: { size: 'compact' }, slots: { title: 'Slot title' } })
    expect(slotted.find('.aui-alert__title').text()).toBe('Slot title')
  })

  it('icon=false hides the icon; the icon slot replaces it', () => {
    expect(mount(BaseAlert, { props: { icon: false, message: 'm' } }).find('.aui-alert__icon').exists()).toBe(false)
    const custom = mount(BaseAlert, { slots: { icon: '<i data-testid="ic" />' } })
    expect(custom.find('[data-testid="ic"]').exists()).toBe(true)
    expect(custom.find('.aui-alert__icon svg').exists()).toBe(false)
  })

  it('bordered adds the bordered class', () => {
    expect(mount(BaseAlert, { props: { bordered: true } }).classes()).toContain('aui-alert--bordered')
  })

  it('renders the actions slot', () => {
    const wrapper = mount(BaseAlert, { slots: { actions: '<button data-testid="act">Retry</button>' } })
    expect(wrapper.find('.aui-alert__actions [data-testid="act"]').exists()).toBe(true)
  })

  it('dismissLabel becomes the dismiss button aria-label', () => {
    const wrapper = mount(BaseAlert, { props: { dismissible: true, dismissLabel: 'Fermer' } })
    expect(wrapper.get('button').attributes('aria-label')).toBe('Fermer')
  })

  it('dismiss hides the alert and emits dismiss once', async () => {
    const wrapper = mount(BaseAlert, { props: { dismissible: true, message: 'm', dismissLabel: 'x' } })
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('dismiss')).toHaveLength(1)
    expect(wrapper.find('.aui-alert').exists()).toBe(false)
  })

  it('a changed message shows the alert again after a dismissal', async () => {
    const wrapper = mount(BaseAlert, { props: { dismissible: true, message: 'a', dismissLabel: 'x' } })
    await wrapper.get('button').trigger('click')
    await wrapper.setProps({ message: 'b' })
    expect(wrapper.text()).toBe('b')
  })

  it('autoDismiss dismisses after the delay and emits', async () => {
    vi.useFakeTimers()
    const wrapper = mount(BaseAlert, { props: { autoDismiss: 3000, message: 'm' } })
    vi.advanceTimersByTime(2999)
    expect(wrapper.emitted('dismiss')).toBeUndefined()
    vi.advanceTimersByTime(1)
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('dismiss')).toHaveLength(1)
    expect(wrapper.find('.aui-alert').exists()).toBe(false)
  })

  it('gives a new message its own full autoDismiss delay', async () => {
    // fails if the first message's timer still fires and cuts the second one short
    vi.useFakeTimers()
    const wrapper = mount(BaseAlert, { props: { autoDismiss: 3000, message: 'first' } })
    vi.advanceTimersByTime(2000)
    await wrapper.setProps({ message: 'second' })
    vi.advanceTimersByTime(1500) // 3500 ms after mount: the old timer would have fired at 3000
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('dismiss')).toBeUndefined()
    expect(wrapper.find('.aui-alert').exists()).toBe(true)
    vi.advanceTimersByTime(1500) // 3000 ms after the new message
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('dismiss')).toHaveLength(1)
  })

  it('autoDismiss changed to 0 cancels the pending dismissal; a positive value starts one', async () => {
    vi.useFakeTimers()
    const wrapper = mount(BaseAlert, { props: { autoDismiss: 3000, message: 'm' } })
    await wrapper.setProps({ autoDismiss: 0 })
    vi.advanceTimersByTime(5000)
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('dismiss')).toBeUndefined()
    await wrapper.setProps({ autoDismiss: 1000 })
    vi.advanceTimersByTime(1000)
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('dismiss')).toHaveLength(1)
  })

  it('a manual dismissal cancels the timer, so dismiss is emitted once', async () => {
    vi.useFakeTimers()
    const wrapper = mount(BaseAlert, {
      props: { autoDismiss: 3000, message: 'm', dismissible: true, dismissLabel: 'Close' },
    })
    await wrapper.find('button').trigger('click')
    vi.advanceTimersByTime(5000)
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('dismiss')).toHaveLength(1)
  })

  it('a message that stays the same keeps its original timer', async () => {
    // contrast: fails if a re-render without a new message restarts the delay
    vi.useFakeTimers()
    const wrapper = mount(BaseAlert, { props: { autoDismiss: 3000, message: 'same', title: 'a' } })
    vi.advanceTimersByTime(2000)
    await wrapper.setProps({ title: 'b' })
    vi.advanceTimersByTime(1000)
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('dismiss')).toHaveLength(1)
  })

  it('reshows a dismissed alert for a new message and dismisses it again on time', async () => {
    vi.useFakeTimers()
    const wrapper = mount(BaseAlert, { props: { autoDismiss: 1000, message: 'one' } })
    vi.advanceTimersByTime(1000)
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.aui-alert').exists()).toBe(false)
    await wrapper.setProps({ message: 'two' })
    expect(wrapper.find('.aui-alert').exists()).toBe(true)
    vi.advanceTimersByTime(1000)
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('dismiss')).toHaveLength(2)
  })

  it('warns when dismissible is set without a dismissLabel', () => {
    // fails if an icon-only dismiss button can render without an accessible name silently
    const spy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    mount(BaseAlert, { props: { message: 'm', dismissible: true } })
    expect(spy.mock.calls.some((c) => String(c[0]).includes('dismissLabel'))).toBe(true)
    spy.mockClear()
    // contrast: a labelled dismissible alert, and a non-dismissible one, stay quiet
    mount(BaseAlert, { props: { message: 'm', dismissible: true, dismissLabel: 'Dismiss' } })
    mount(BaseAlert, { props: { message: 'm' } })
    expect(spy.mock.calls.some((c) => String(c[0]).includes('dismissLabel'))).toBe(false)
    spy.mockRestore()
  })

  it('clears the autoDismiss timer on unmount', () => {
    vi.useFakeTimers()
    const wrapper = mount(BaseAlert, { props: { autoDismiss: 3000, message: 'm' } })
    wrapper.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('never sets a box-shadow (design system rule, #18691)', () => {
    const style = alertSource.slice(alertSource.indexOf('<style'))
    expect(style).not.toMatch(/box-shadow/)
  })
})
