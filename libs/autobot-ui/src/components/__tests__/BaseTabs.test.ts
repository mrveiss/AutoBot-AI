// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BaseTabs (#14779): roles and aria wiring, roving tabindex, Arrow/Home/End, disabled skip,
// manual activation, v-model, and the arrow-key direction under dir="rtl".

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import BaseTabs from '../BaseTabs.vue'
import { installRekaDomStubs, press } from './rekaTestEnv'

const ITEMS = [
  { value: 'one', label: 'First' },
  { value: 'two', label: 'Second', disabled: true },
  { value: 'three', label: 'Third' },
  { value: 'four', label: 'Fourth' },
]

let wrapper: VueWrapper | undefined

async function render(props: Record<string, unknown> = {}) {
  wrapper = mount(BaseTabs, {
    props: { items: ITEMS, label: 'Sections', ...props },
    slots: { 'panel-one': 'Panel one', 'panel-three': 'Panel three', 'panel-four': 'Panel four' },
    attachTo: document.body,
  })
  await flushPromises()
  return wrapper
}

const tabs = () => Array.from(document.querySelectorAll<HTMLElement>('[role="tab"]'))
const selected = () => tabs().findIndex((t) => t.getAttribute('aria-selected') === 'true')

beforeEach(installRekaDomStubs)
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  document.documentElement.removeAttribute('dir')
})

describe('BaseTabs roles and aria', () => {
  it('renders a named tablist, tabs and the selected tabpanel, wired by aria-controls', async () => {
    await render()
    const list = document.querySelector('[role="tablist"]')
    expect(list?.getAttribute('aria-label')).toBe('Sections')
    expect(tabs()).toHaveLength(ITEMS.length)
    expect(selected()).toBe(0)
    const panel = document.querySelector('[role="tabpanel"]:not([hidden])')
    expect(panel?.textContent).toContain('Panel one')
    expect(tabs()[0].getAttribute('aria-controls')).toBe(panel?.id)
    expect(panel?.getAttribute('aria-labelledby')).toBe(tabs()[0].id)
  })

  it('roving tabindex: the tablist takes the tab stop, then only the focused tab does', async () => {
    await render()
    expect(document.querySelector('[role="tablist"]')?.getAttribute('tabindex')).toBe('0')
    expect(tabs().every((t) => t.getAttribute('tabindex') === '-1')).toBe(true)
    tabs()[0].focus()
    await press(tabs()[0], 'ArrowRight')
    expect(tabs()[2].getAttribute('tabindex')).toBe('0')
    expect(tabs()[0].getAttribute('tabindex')).toBe('-1')
  })

  it('renders only the selected panel visible; the others are hidden', async () => {
    await render()
    const hidden = document.querySelectorAll('[role="tabpanel"][hidden]')
    expect(hidden).toHaveLength(ITEMS.length - 1)
  })

  it('marks a disabled tab disabled', async () => {
    await render()
    expect(tabs()[1].hasAttribute('disabled')).toBe(true)
  })

  it('reports vertical orientation on the tablist', async () => {
    await render({ orientation: 'vertical' })
    expect(document.querySelector('[role="tablist"]')?.getAttribute('aria-orientation')).toBe('vertical')
  })

  it('applies the variant and size classes', async () => {
    const w = await render({ variant: 'pill', size: 'sm' })
    expect(w.classes()).toEqual(expect.arrayContaining(['aui-tabs--pill', 'aui-tabs--sm']))
  })
})

describe('BaseTabs keyboard', () => {
  it('ArrowRight moves focus and selection to the next enabled tab, skipping a disabled one', async () => {
    await render()
    tabs()[0].focus()
    await press(tabs()[0], 'ArrowRight')
    expect(document.activeElement).toBe(tabs()[2])
    expect(selected()).toBe(2)
  })

  it('ArrowLeft from the first tab wraps to the last', async () => {
    await render()
    tabs()[0].focus()
    await press(tabs()[0], 'ArrowLeft')
    expect(document.activeElement).toBe(tabs()[3])
  })

  it('End focuses the last tab and Home the first', async () => {
    await render()
    tabs()[0].focus()
    await press(tabs()[0], 'End')
    expect(document.activeElement).toBe(tabs()[3])
    await press(tabs()[3], 'Home')
    expect(document.activeElement).toBe(tabs()[0])
  })

  it('vertical tabs move with ArrowDown and ArrowUp', async () => {
    await render({ orientation: 'vertical' })
    tabs()[0].focus()
    await press(tabs()[0], 'ArrowDown')
    expect(document.activeElement).toBe(tabs()[2])
    await press(tabs()[2], 'ArrowUp')
    expect(document.activeElement).toBe(tabs()[0])
  })

  it('manual activation moves focus without selecting until Enter', async () => {
    await render({ activationMode: 'manual' })
    tabs()[0].focus()
    await press(tabs()[0], 'ArrowRight')
    expect(document.activeElement).toBe(tabs()[2])
    expect(selected()).toBe(0)
    await press(tabs()[2], 'Enter')
    expect(selected()).toBe(2)
  })

  it('emits update:modelValue with the new value', async () => {
    const w = await render()
    tabs()[0].focus()
    await press(tabs()[0], 'ArrowRight')
    expect(w.emitted('update:modelValue')).toEqual([['three']])
  })

  it('follows a controlled modelValue', async () => {
    await render({ modelValue: 'four' })
    expect(selected()).toBe(3)
    expect(document.querySelector('[role="tabpanel"]:not([hidden])')?.textContent).toContain('Panel four')
  })
})

describe('BaseTabs RTL', () => {
  it('dir="rtl": ArrowRight moves to the previous tab and ArrowLeft to the next', async () => {
    await render({ dir: 'rtl', defaultValue: 'three' })
    tabs()[2].focus()
    await press(tabs()[2], 'ArrowRight')
    expect(document.activeElement).toBe(tabs()[0])
    await press(tabs()[0], 'ArrowLeft')
    expect(document.activeElement).toBe(tabs()[2])
  })

  it('dir="ltr" keeps ArrowRight as next', async () => {
    await render({ dir: 'ltr' })
    tabs()[0].focus()
    await press(tabs()[0], 'ArrowRight')
    expect(document.activeElement).toBe(tabs()[2])
  })

  it('follows the document direction when no dir prop is passed', async () => {
    document.documentElement.dir = 'rtl'
    await render({ defaultValue: 'three' })
    tabs()[2].focus()
    await press(tabs()[2], 'ArrowRight')
    expect(document.activeElement).toBe(tabs()[0])
  })
})
