// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BaseDropdownMenu (#14779): trigger aria, menu/menuitem roles, keyboard opening, Arrow/Home/End
// navigation, disabled skip, select, Escape closing, and the arrow direction under dir="rtl".

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { h } from 'vue'
import BaseDropdownMenu from '../BaseDropdownMenu.vue'
import { installRekaDomStubs, press } from './rekaTestEnv'

const ITEMS = [
  { key: 'rename', label: 'Rename' },
  { key: 'copy', label: 'Copy', disabled: true },
  { key: 'move', label: 'Move', separatorBefore: true },
  { key: 'delete', label: 'Delete', variant: 'danger' as const },
]

let wrapper: VueWrapper | undefined

async function render(props: Record<string, unknown> = {}) {
  wrapper = mount(BaseDropdownMenu, {
    props: { items: ITEMS, ...props },
    slots: { trigger: () => h('button', { type: 'button', 'data-testid': 'trigger' }, 'Actions') },
    attachTo: document.body,
  })
  await flushPromises()
  return wrapper
}

const trigger = () => document.querySelector('[data-testid="trigger"]') as HTMLElement
const menu = () => document.querySelector<HTMLElement>('[role="menu"]')
const items = () => Array.from(document.querySelectorAll<HTMLElement>('[role="menuitem"]'))

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

describe('BaseDropdownMenu roles and aria', () => {
  it('the trigger advertises a menu and starts collapsed', async () => {
    await render()
    expect(trigger().getAttribute('aria-haspopup')).toBe('menu')
    expect(trigger().getAttribute('aria-expanded')).toBe('false')
    expect(menu()).toBeNull()
  })

  it('opening exposes a menu named by its trigger, with menuitems, and sets aria-expanded', async () => {
    await render()
    await openWithKey('Enter')
    expect(menu()).not.toBeNull()
    expect(trigger().getAttribute('aria-expanded')).toBe('true')
    expect(menu()?.getAttribute('aria-labelledby')).toBe(trigger().id)
    expect(items().map((i) => i.textContent?.trim())).toEqual(['Rename', 'Copy', 'Move', 'Delete'])
  })

  it('marks a disabled item aria-disabled and renders a separator', async () => {
    await render()
    await openWithKey('Enter')
    expect(items()[1].getAttribute('aria-disabled')).toBe('true')
    expect(document.querySelectorAll('[role="separator"]')).toHaveLength(1)
  })

  it('applies the size and item variant classes', async () => {
    await render({ size: 'sm' })
    await openWithKey('Enter')
    expect(menu()?.classList.contains('aui-menu--sm')).toBe(true)
    expect(items()[3].classList.contains('aui-menu__item--danger')).toBe(true)
  })
})

describe('BaseDropdownMenu keyboard', () => {
  it('ArrowDown on the trigger opens the menu and focuses the first item', async () => {
    await render()
    await openWithKey('ArrowDown')
    expect(menu()).not.toBeNull()
    expect(document.activeElement).toBe(items()[0])
  })

  it('Space on the trigger opens the menu', async () => {
    await render()
    await openWithKey(' ')
    expect(menu()).not.toBeNull()
  })

  it('ArrowDown and ArrowUp move between enabled items', async () => {
    await render()
    await openWithKey('ArrowDown')
    await press(document.activeElement, 'ArrowDown')
    expect(document.activeElement).toBe(items()[2])
    await press(document.activeElement, 'ArrowUp')
    expect(document.activeElement).toBe(items()[0])
  })

  it('End focuses the last item and Home the first', async () => {
    await render()
    await openWithKey('ArrowDown')
    await press(document.activeElement, 'End')
    expect(document.activeElement).toBe(items()[3])
    await press(document.activeElement, 'Home')
    expect(document.activeElement).toBe(items()[0])
  })

  it('Enter on an item emits select with its key and closes the menu', async () => {
    const w = await render()
    await openWithKey('ArrowDown')
    await press(document.activeElement, 'ArrowDown')
    await press(document.activeElement, 'Enter')
    await flushPromises()
    expect(w.emitted('select')).toEqual([['move']])
    expect(menu()).toBeNull()
  })

  it('Escape closes the menu and returns focus to the trigger', async () => {
    const w = await render()
    await openWithKey('ArrowDown')
    await press(document.activeElement, 'Escape')
    await flushPromises()
    expect(menu()).toBeNull()
    expect(w.emitted('update:open')?.at(-1)).toEqual([false])
    await vi.waitFor(() => expect(document.activeElement).toBe(trigger()))
  })

  it('a disabled item never emits select', async () => {
    const w = await render({ open: true })
    items()[1].click()
    await flushPromises()
    expect(w.emitted('select')).toBeUndefined()
  })
})

describe('BaseDropdownMenu RTL', () => {
  it('dir="rtl" opens the menu from the trigger and keeps vertical arrows vertical', async () => {
    await render({ dir: 'rtl' })
    await openWithKey('ArrowDown')
    expect(document.activeElement).toBe(items()[0])
    await press(document.activeElement, 'ArrowDown')
    expect(document.activeElement).toBe(items()[2])
    expect(menu()?.getAttribute('dir')).toBe('rtl')
  })

  it('follows the document direction when no dir prop is passed', async () => {
    document.documentElement.dir = 'rtl'
    await render()
    await openWithKey('Enter')
    expect(menu()?.getAttribute('dir')).toBe('rtl')
  })

  it('dir="ltr" renders the menu left-to-right', async () => {
    await render({ dir: 'ltr' })
    await openWithKey('Enter')
    expect(menu()?.getAttribute('dir')).toBe('ltr')
  })
})
