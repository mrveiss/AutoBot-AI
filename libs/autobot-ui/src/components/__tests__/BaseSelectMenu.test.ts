// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BaseSelectMenu (#14779): combobox/listbox/option roles and aria, keyboard opening, Arrow/Home/End
// navigation, disabled skip, choosing with Enter, Escape, placeholder, and dir="rtl".

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import BaseSelectMenu from '../BaseSelectMenu.vue'
import { installRekaDomStubs, press } from './rekaTestEnv'

const OPTIONS = [
  { value: 'red', label: 'Red' },
  { value: 'green', label: 'Green', disabled: true },
  { value: 'blue', label: 'Blue' },
  { value: 'cyan', label: 'Cyan' },
]

let wrapper: VueWrapper | undefined

async function render(props: Record<string, unknown> = {}) {
  wrapper = mount(BaseSelectMenu, {
    props: { options: OPTIONS, label: 'Colour', placeholder: 'Pick one', ...props },
    attachTo: document.body,
  })
  await flushPromises()
  return wrapper
}

const trigger = () => document.querySelector<HTMLElement>('[role="combobox"]') as HTMLElement
const listbox = () => document.querySelector<HTMLElement>('[role="listbox"]')
const options = () => Array.from(document.querySelectorAll<HTMLElement>('[role="option"]'))

async function openWithKey(key: string) {
  trigger().focus()
  await press(trigger(), key)
  await flushPromises()
}

beforeEach(installRekaDomStubs)
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  document.body.innerHTML = ''
  document.documentElement.removeAttribute('dir')
})

describe('BaseSelectMenu roles and aria', () => {
  it('the trigger is a named combobox, collapsed, showing the placeholder', async () => {
    await render()
    expect(trigger().getAttribute('aria-label')).toBe('Colour')
    expect(trigger().getAttribute('aria-expanded')).toBe('false')
    expect(trigger().textContent).toContain('Pick one')
    expect(listbox()).toBeNull()
  })

  it('opening exposes a listbox of options and sets aria-expanded', async () => {
    await render()
    await openWithKey('Enter')
    expect(listbox()).not.toBeNull()
    expect(trigger().getAttribute('aria-expanded')).toBe('true')
    expect(options().map((o) => o.textContent?.trim())).toEqual(['Red', 'Green', 'Blue', 'Cyan'])
  })

  it('marks the chosen option aria-selected and shows it in the trigger', async () => {
    await render({ modelValue: 'blue' })
    expect(trigger().textContent).toContain('Blue')
    await openWithKey('Enter')
    expect(options().map((o) => o.getAttribute('aria-selected'))).toEqual(['false', 'false', 'true', 'false'])
  })

  it('marks a disabled option aria-disabled', async () => {
    await render()
    await openWithKey('Enter')
    expect(options()[1].getAttribute('aria-disabled')).toBe('true')
  })

  it('applies the size and variant classes', async () => {
    await render({ size: 'lg', variant: 'subtle' })
    expect(trigger().classList.contains('aui-select__trigger--lg')).toBe(true)
    expect(trigger().classList.contains('aui-select__trigger--subtle')).toBe(true)
  })

  it('a disabled control does not open', async () => {
    await render({ disabled: true })
    await openWithKey('Enter')
    expect(listbox()).toBeNull()
  })
})

describe('BaseSelectMenu keyboard', () => {
  it('ArrowDown on the trigger opens the list', async () => {
    await render()
    await openWithKey('ArrowDown')
    expect(listbox()).not.toBeNull()
  })

  it('ArrowDown and ArrowUp move between enabled options', async () => {
    await render()
    await openWithKey('Enter')
    options()[0].focus()
    await press(options()[0], 'ArrowDown')
    expect(document.activeElement).toBe(options()[2])
    await press(options()[2], 'ArrowUp')
    expect(document.activeElement).toBe(options()[0])
  })

  it('End focuses the last option and Home the first', async () => {
    await render()
    await openWithKey('Enter')
    options()[0].focus()
    await press(options()[0], 'End')
    expect(document.activeElement).toBe(options()[3])
    await press(options()[3], 'Home')
    expect(document.activeElement).toBe(options()[0])
  })

  it('Enter on an option emits update:modelValue and closes the list', async () => {
    const w = await render()
    await openWithKey('Enter')
    options()[0].focus()
    await press(options()[0], 'ArrowDown')
    await press(options()[2], 'Enter')
    await flushPromises()
    expect(w.emitted('update:modelValue')).toEqual([['blue']])
    expect(listbox()).toBeNull()
  })

  it('Escape closes the list without choosing and returns focus to the trigger', async () => {
    const w = await render()
    await openWithKey('Enter')
    await press(document.activeElement, 'Escape')
    await flushPromises()
    expect(listbox()).toBeNull()
    expect(w.emitted('update:modelValue')).toBeUndefined()
    expect(document.activeElement).toBe(trigger())
  })
})

describe('BaseSelectMenu RTL', () => {
  it('dir="rtl" renders the list right-to-left and keeps vertical arrows vertical', async () => {
    await render({ dir: 'rtl' })
    await openWithKey('Enter')
    expect(listbox()?.closest('[dir]')?.getAttribute('dir')).toBe('rtl')
    options()[0].focus()
    await press(options()[0], 'ArrowDown')
    expect(document.activeElement).toBe(options()[2])
  })

  it('follows the document direction when no dir prop is passed', async () => {
    document.documentElement.dir = 'rtl'
    await render()
    await openWithKey('Enter')
    expect(listbox()?.closest('[dir]')?.getAttribute('dir')).toBe('rtl')
  })
})
