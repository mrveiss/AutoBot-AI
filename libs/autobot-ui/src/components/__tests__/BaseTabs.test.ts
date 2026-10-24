// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BaseTabs (#14779): the WAI-ARIA tabs pattern through Reka UI — a named tablist, one tab per
// item wired to its panel, roving tabindex, Arrow / Home / End that skip disabled tabs and
// mirror in RTL, and manual activation that waits for Enter / Space.

import { describe, it, expect, afterEach } from 'vitest'
import { nextTick } from 'vue'
import { mount, type VueWrapper } from '@vue/test-utils'
import BaseTabs from '../BaseTabs.vue'

const tabs = [
  { value: 'overview', label: 'Overview' },
  { value: 'logs', label: 'Logs' },
  { value: 'locked', label: 'Locked', disabled: true },
  { value: 'settings', label: 'Settings' },
]

let wrapper: VueWrapper | undefined

function render(props: Record<string, unknown> = {}) {
  wrapper = mount(BaseTabs, {
    props: {
      modelValue: 'overview',
      tabs,
      label: 'Sections',
      'onUpdate:modelValue': (v: string) => wrapper?.setProps({ modelValue: v }),
      ...props,
    },
    slots: { panel: '<template #panel="{ tab }"><p class="body">{{ tab.label }} body</p></template>' },
    attachTo: document.body,
  })
  return wrapper
}

const tabEls = (w: VueWrapper) => w.findAll('[role="tab"]')
// Reka moves focus on a timer, not a microtask
const settle = () => new Promise((resolve) => setTimeout(resolve, 20))
const focusOn = async (el: Element) => {
  ;(el as HTMLElement).focus()
  await settle()
}
const press = async (el: Element, key: string) => {
  el.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }))
  await settle()
}

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  document.documentElement.dir = ''
})

describe('BaseTabs', () => {
  it('is a named tablist whose selected tab controls the visible panel', async () => {
    const w = render()
    await nextTick()
    expect(w.find('[role="tablist"]').attributes('aria-label')).toBe('Sections')
    const [first, second] = tabEls(w)
    expect(first.attributes('aria-selected')).toBe('true')
    expect(second.attributes('aria-selected')).toBe('false')
    const panel = w.find('[role="tabpanel"]:not([hidden])')
    expect(panel.attributes('id')).toBe(first.attributes('aria-controls'))
    expect(panel.attributes('aria-labelledby')).toBe(first.attributes('id'))
    expect(panel.text()).toBe('Overview body')
  })

  it('is one tab stop: only the focused tab is tabbable (roving tabindex)', async () => {
    const w = render({ modelValue: 'logs' })
    await focusOn(tabEls(w)[1].element)
    expect(tabEls(w).map((t) => t.attributes('tabindex'))).toEqual(['-1', '0', '-1', '-1'])
    await press(tabEls(w)[1].element, 'ArrowRight')
    expect(tabEls(w).map((t) => t.attributes('tabindex'))).toEqual(['-1', '-1', '-1', '0'])
  })

  it('ArrowRight moves to and selects the next tab, skipping a disabled one', async () => {
    const w = render({ modelValue: 'logs' })
    await focusOn(tabEls(w)[1].element)
    await press(tabEls(w)[1].element, 'ArrowRight')
    expect(document.activeElement).toBe(tabEls(w)[3].element)
    expect(w.emitted('update:modelValue')?.at(-1)).toEqual(['settings'])
  })

  it('Home and End jump to the first and last tab', async () => {
    const w = render({ modelValue: 'logs' })
    await focusOn(tabEls(w)[1].element)
    await press(tabEls(w)[1].element, 'End')
    expect(document.activeElement).toBe(tabEls(w)[3].element)
    await press(tabEls(w)[3].element, 'Home')
    expect(document.activeElement).toBe(tabEls(w)[0].element)
  })

  it('mirrors the arrow keys when the document is right-to-left', async () => {
    document.documentElement.dir = 'rtl'
    await nextTick()
    const w = render()
    await focusOn(tabEls(w)[0].element)
    await press(tabEls(w)[0].element, 'ArrowLeft')
    expect(document.activeElement).toBe(tabEls(w)[1].element)
  })

  it('manual activation moves focus without selecting until Enter', async () => {
    const w = render({ activation: 'manual' })
    await focusOn(tabEls(w)[0].element)
    await press(tabEls(w)[0].element, 'ArrowRight')
    expect(document.activeElement).toBe(tabEls(w)[1].element)
    expect(w.emitted('update:modelValue')).toBeUndefined()
    await tabEls(w)[1].trigger('mousedown')
    await press(tabEls(w)[1].element, 'Enter')
    expect(w.emitted('update:modelValue')?.at(-1)).toEqual(['logs'])
  })

  it('a disabled tab is marked and cannot be selected by click', async () => {
    const w = render()
    const locked = tabEls(w)[2]
    expect(locked.attributes('disabled')).toBeDefined()
    await locked.trigger('mousedown')
    expect(w.emitted('update:modelValue')).toBeUndefined()
  })

  it('takes trigger content from the tab slot', () => {
    wrapper = mount(BaseTabs, {
      props: { modelValue: 'logs', tabs, label: 'Sections' },
      slots: { tab: '<template #tab="{ tab, selected }"><b>{{ tab.label }}{{ selected ? "*" : "" }}</b></template>' },
    })
    expect(tabEls(wrapper).map((t) => t.text())).toEqual(['Overview', 'Logs*', 'Locked', 'Settings'])
  })
})
