// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BaseAccordion (#14779): heading + button structure, aria-expanded/aria-controls, region panels,
// single vs multiple, collapsible, Arrow/Home/End focus movement, disabled skip, and the
// mirrored Left/Right arrows of a horizontal accordion under dir="rtl".

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import BaseAccordion from '../BaseAccordion.vue'
import { installRekaDomStubs, press } from './rekaTestEnv'

const ITEMS = [
  { value: 'a', label: 'Alpha' },
  { value: 'b', label: 'Beta', disabled: true },
  { value: 'c', label: 'Gamma' },
  { value: 'd', label: 'Delta' },
]

let wrapper: VueWrapper | undefined

async function render(props: Record<string, unknown> = {}) {
  wrapper = mount(BaseAccordion, {
    props: { items: ITEMS, ...props },
    slots: { 'panel-a': 'Body A', 'panel-c': 'Body C', 'panel-d': 'Body D' },
    attachTo: document.body,
  })
  await flushPromises()
  return wrapper
}

const triggers = () => Array.from(document.querySelectorAll<HTMLElement>('button[aria-expanded]'))
const expanded = () => triggers().map((t) => t.getAttribute('aria-expanded') === 'true')
const regions = () => Array.from(document.querySelectorAll<HTMLElement>('[role="region"]'))

async function toggle(index: number) {
  triggers()[index].click()
  await flushPromises()
}

beforeEach(installRekaDomStubs)
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  document.body.innerHTML = ''
  document.documentElement.removeAttribute('dir')
})

describe('BaseAccordion roles and aria', () => {
  it('exposes each section title as a heading containing a button', async () => {
    await render()
    const headings = Array.from(document.querySelectorAll('h3'))
    expect(headings).toHaveLength(ITEMS.length)
    expect(headings[0].querySelector('button')?.textContent).toContain('Alpha')
  })

  it('headingLevel changes the heading element', async () => {
    await render({ headingLevel: 2 })
    expect(document.querySelectorAll('h2')).toHaveLength(ITEMS.length)
    expect(document.querySelectorAll('h3')).toHaveLength(0)
  })

  it('starts collapsed, and opening sets aria-expanded and shows a region labelled by its trigger', async () => {
    await render()
    expect(expanded()).toEqual([false, false, false, false])
    await toggle(0)
    expect(expanded()[0]).toBe(true)
    const region = regions()[0]
    expect(region.textContent).toContain('Body A')
    expect(triggers()[0].getAttribute('aria-controls')).toBe(region.id)
    expect(region.getAttribute('aria-labelledby')).toBe(triggers()[0].id)
  })

  it('marks a disabled section disabled', async () => {
    await render()
    expect(triggers()[1].hasAttribute('disabled')).toBe(true)
  })

  it('applies the variant and size classes', async () => {
    const w = await render({ variant: 'flush', size: 'sm' })
    expect(w.classes()).toEqual(expect.arrayContaining(['aui-accordion--flush', 'aui-accordion--sm']))
  })
})

describe('BaseAccordion open state', () => {
  it('single: opening one section closes the other', async () => {
    await render({ defaultValue: 'a' })
    await toggle(2)
    expect(expanded()).toEqual([false, false, true, false])
  })

  it('single + collapsible: clicking the open section closes it', async () => {
    await render({ defaultValue: 'a' })
    await toggle(0)
    expect(expanded()[0]).toBe(false)
  })

  it('single without collapsible: the open section stays open', async () => {
    await render({ defaultValue: 'a', collapsible: false })
    await toggle(0)
    expect(expanded()[0]).toBe(true)
  })

  it('multiple: several sections can be open and v-model is an array', async () => {
    const w = await render({ type: 'multiple', defaultValue: [] })
    await toggle(0)
    await toggle(2)
    expect(expanded()).toEqual([true, false, true, false])
    expect(w.emitted('update:modelValue')?.at(-1)).toEqual([['a', 'c']])
  })

  it('follows a controlled modelValue', async () => {
    await render({ modelValue: 'd' })
    expect(expanded()).toEqual([false, false, false, true])
  })
})

describe('BaseAccordion keyboard', () => {
  it('ArrowDown moves focus to the next enabled trigger, skipping a disabled one', async () => {
    await render()
    triggers()[0].focus()
    await press(triggers()[0], 'ArrowDown')
    expect(document.activeElement).toBe(triggers()[2])
  })

  it('ArrowUp from the first trigger wraps to the last', async () => {
    await render()
    triggers()[0].focus()
    await press(triggers()[0], 'ArrowUp')
    expect(document.activeElement).toBe(triggers()[3])
  })

  it('End focuses the last trigger and Home the first', async () => {
    await render()
    triggers()[0].focus()
    await press(triggers()[0], 'End')
    expect(document.activeElement).toBe(triggers()[3])
    await press(triggers()[3], 'Home')
    expect(document.activeElement).toBe(triggers()[0])
  })
})

describe('BaseAccordion RTL', () => {
  it('horizontal + dir="ltr": ArrowRight moves to the next trigger', async () => {
    await render({ orientation: 'horizontal', dir: 'ltr' })
    triggers()[0].focus()
    await press(triggers()[0], 'ArrowRight')
    expect(document.activeElement).toBe(triggers()[2])
  })

  it('horizontal + dir="rtl": ArrowRight moves to the previous trigger and ArrowLeft to the next', async () => {
    await render({ orientation: 'horizontal', dir: 'rtl', defaultValue: 'c' })
    triggers()[2].focus()
    await press(triggers()[2], 'ArrowRight')
    expect(document.activeElement).toBe(triggers()[0])
    await press(triggers()[0], 'ArrowLeft')
    expect(document.activeElement).toBe(triggers()[2])
  })

  it('horizontal: follows the document direction when no dir prop is passed', async () => {
    document.documentElement.dir = 'rtl'
    await render({ orientation: 'horizontal' })
    triggers()[2].focus()
    await press(triggers()[2], 'ArrowRight')
    expect(document.activeElement).toBe(triggers()[0])
  })

  it('vertical + dir="rtl": ArrowDown is still next', async () => {
    await render({ dir: 'rtl' })
    triggers()[0].focus()
    await press(triggers()[0], 'ArrowDown')
    expect(document.activeElement).toBe(triggers()[2])
  })
})
