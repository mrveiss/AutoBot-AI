// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BaseAccordion (#14779): the WAI-ARIA accordion pattern through Reka UI — each header is a
// heading wrapping a button with aria-expanded / aria-controls, its panel a region labelled
// by it; single and multiple modes; Arrow / Home / End move between headers.

import { describe, it, expect, afterEach } from 'vitest'
import { nextTick } from 'vue'
import { mount, type VueWrapper } from '@vue/test-utils'
import BaseAccordion from '../BaseAccordion.vue'

const items = [
  { value: 'a', label: 'General' },
  { value: 'b', label: 'Network' },
  { value: 'c', label: 'Danger zone', disabled: true },
]

let wrapper: VueWrapper | undefined

function render(props: Record<string, unknown> = {}) {
  wrapper = mount(BaseAccordion, {
    props: {
      items,
      'onUpdate:modelValue': (v: unknown) => wrapper?.setProps({ modelValue: v }),
      ...props,
    },
    slots: { panel: '<template #panel="{ item }"><p class="body">{{ item.label }} body</p></template>' },
    attachTo: document.body,
  })
  return wrapper
}

const triggers = (w: VueWrapper) => w.findAll('button.aui-accordion__trigger')
// Reka records the focused header and moves focus on a timer, not a microtask
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
})

describe('BaseAccordion', () => {
  it('wraps each trigger in a heading at the given level', () => {
    const w = render({ level: 4 })
    expect(w.findAll('h4 > button.aui-accordion__trigger')).toHaveLength(3)
  })

  it('a click opens an item: aria-expanded flips and its region is labelled by the trigger', async () => {
    const w = render()
    const t = triggers(w)[0]
    expect(t.attributes('aria-expanded')).toBe('false')
    await t.trigger('click')
    expect(w.emitted('update:modelValue')?.at(-1)).toEqual(['a'])
    await nextTick()
    expect(t.attributes('aria-expanded')).toBe('true')
    const region = w.find(`#${t.attributes('aria-controls')}`)
    expect(region.attributes('role')).toBe('region')
    expect(region.attributes('aria-labelledby')).toBe(t.attributes('id'))
    expect(region.text()).toBe('General body')
  })

  it('single mode keeps one item open; collapsible lets it close', async () => {
    const w = render({ modelValue: 'a' })
    await triggers(w)[1].trigger('click')
    expect(w.emitted('update:modelValue')?.at(-1)).toEqual(['b'])
    await nextTick()
    await triggers(w)[1].trigger('click')
    expect(w.emitted('update:modelValue')?.at(-1)?.[0] ?? '').toBe('')
  })

  it('multiple mode keeps several open', async () => {
    const w = render({ type: 'multiple', modelValue: ['a'] })
    await triggers(w)[1].trigger('click')
    expect(w.emitted('update:modelValue')?.at(-1)).toEqual([['a', 'b']])
  })

  it('ArrowDown moves focus to the next header, skipping a disabled one and wrapping', async () => {
    const w = render()
    await focusOn(triggers(w)[0].element)
    await press(triggers(w)[0].element, 'ArrowDown')
    expect(document.activeElement).toBe(triggers(w)[1].element)
    await press(triggers(w)[1].element, 'ArrowDown')
    expect(document.activeElement).toBe(triggers(w)[0].element)
  })

  it('Home and End jump to the first and last header', async () => {
    const w = render({ items: items.slice(0, 2).concat({ value: 'd', label: 'Storage' }) })
    await focusOn(triggers(w)[0].element)
    await press(triggers(w)[0].element, 'End')
    expect(document.activeElement).toBe(triggers(w)[2].element)
    await press(triggers(w)[2].element, 'Home')
    expect(document.activeElement).toBe(triggers(w)[0].element)
  })

  it('a disabled item is marked and does not open', async () => {
    const w = render()
    const t = triggers(w)[2]
    expect(t.attributes('disabled')).toBeDefined()
    await t.trigger('click')
    expect(w.emitted('update:modelValue')).toBeUndefined()
  })

  it('takes header content from the label slot with its open state', async () => {
    wrapper = mount(BaseAccordion, {
      props: { items, modelValue: 'b' },
      slots: { label: '<template #label="{ item, open }">{{ item.label }}{{ open ? " (open)" : "" }}</template>' },
    })
    expect(triggers(wrapper).map((t) => t.text())).toEqual(['General', 'Network (open)', 'Danger zone'])
  })
})
