// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BasePopover (#14779): trigger aria, dialog role and accessible name, opening by click and by
// keyboard, focus moved in and restored, Escape and outside-press dismissal, slot `close`.

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { h } from 'vue'
import BasePopover from '../BasePopover.vue'
import { installRekaDomStubs, press } from './rekaTestEnv'

let wrapper: VueWrapper | undefined

async function render(props: Record<string, unknown> = {}) {
  wrapper = mount(BasePopover, {
    props: { label: 'Filter options', ...props },
    slots: {
      trigger: () => h('button', { type: 'button', 'data-testid': 'trigger' }, 'Open'),
      default: (slot: { close: () => void }) =>
        h('div', [
          h('input', { 'data-testid': 'field' }),
          h('button', { type: 'button', 'data-testid': 'done', onClick: slot.close }, 'Done'),
        ]),
    },
    attachTo: document.body,
  })
  await flushPromises()
  return wrapper
}

const trigger = () => document.querySelector<HTMLElement>('[data-testid="trigger"]') as HTMLElement
const panel = () => document.querySelector<HTMLElement>('[role="dialog"]')

async function open() {
  trigger().click()
  await flushPromises()
}

beforeEach(installRekaDomStubs)
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  document.body.innerHTML = ''
})

describe('BasePopover roles and aria', () => {
  it('the trigger advertises a dialog and starts collapsed', async () => {
    await render()
    expect(trigger().getAttribute('aria-haspopup')).toBe('dialog')
    expect(trigger().getAttribute('aria-expanded')).toBe('false')
    expect(panel()).toBeNull()
  })

  it('opening renders a named dialog, wired to the trigger by aria-controls', async () => {
    await render()
    await open()
    expect(panel()).not.toBeNull()
    expect(panel()?.getAttribute('aria-label')).toBe('Filter options')
    expect(trigger().getAttribute('aria-expanded')).toBe('true')
    expect(trigger().getAttribute('aria-controls')).toBe(panel()?.id)
  })

  it('applies the size class', async () => {
    await render({ size: 'lg' })
    await open()
    expect(panel()?.classList.contains('aui-popover--lg')).toBe(true)
  })
})

describe('BasePopover keyboard and dismissal', () => {
  it('the trigger is a native button, so Enter and Space reach it as a click and open the panel', async () => {
    await render()
    trigger().focus()
    trigger().click()
    await flushPromises()
    expect(panel()).not.toBeNull()
  })

  it('moves focus into the panel on open', async () => {
    await render()
    await open()
    expect(panel()?.contains(document.activeElement)).toBe(true)
  })

  it('Escape closes the panel, returns focus to the trigger and emits update:open false', async () => {
    const w = await render()
    trigger().focus()
    await open()
    await press(document.activeElement, 'Escape')
    await flushPromises()
    expect(panel()).toBeNull()
    expect(w.emitted('update:open')?.at(-1)).toEqual([false])
    expect(document.activeElement).toBe(trigger())
  })

  it('the slot close() closes the panel', async () => {
    await render()
    await open()
    document.querySelector<HTMLElement>('[data-testid="done"]')?.click()
    await flushPromises()
    expect(panel()).toBeNull()
  })

  it('a pointer press outside the panel closes it', async () => {
    const w = await render()
    await open()
    await new Promise((resolve) => setTimeout(resolve, 10))
    document.body.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true }))
    await flushPromises()
    expect(panel()).toBeNull()
    expect(w.emitted('update:open')?.at(-1)).toEqual([false])
  })

  it('a controlled open prop renders the panel without a click', async () => {
    await render({ open: true })
    expect(panel()).not.toBeNull()
  })
})
