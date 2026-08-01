// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * BaseModal focus-trap tests (#5016)
 *
 * Covers the real Tab / Shift+Tab wrap behavior that replaces the old
 * focusin snap-to-first-element pattern which broke keyboard wrap
 * and bounced focus back on every outside click.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { BaseModal } from '@autobot/ui'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      ui: { modal: { closeDialog: 'Close dialog' } }
    }
  }
})

const mountModal = (slots?: Record<string, string>) =>
  mount(BaseModal, {
    props: { modelValue: true, title: 'Test' },
    slots: {
      default: '<button class="body-btn">Body</button>',
      actions: '<button class="cancel">Cancel</button><button class="confirm">OK</button>',
      ...slots,
    },
    global: {
      plugins: [i18n],
      stubs: { Teleport: true, Transition: false, Icon: true },
    },
    attachTo: document.body,
  })

const dispatchTab = (el: Element, shiftKey = false) => {
  const event = new KeyboardEvent('keydown', {
    key: 'Tab',
    bubbles: true,
    cancelable: true,
    shiftKey,
  })
  el.dispatchEvent(event)
  return event
}

const getFocusables = (root: Element) =>
  Array.from(
    root.querySelectorAll<HTMLElement>(
      'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])'
    )
  )

describe('BaseModal focus trap (#5016)', () => {
  beforeEach(() => {
    document.body.replaceChildren()
  })

  it('renders the dialog with a close button and slotted content', async () => {
    const wrapper = mountModal()
    await flushPromises()
    const dialog = wrapper.find('[role="dialog"]')
    expect(dialog.exists()).toBe(true)
    expect(dialog.find('.aui-dialog-close').exists()).toBe(true)
    expect(dialog.find('.body-btn').exists()).toBe(true)
    wrapper.unmount()
  })

  it('Shift+Tab on the first focusable wraps focus to the last', async () => {
    const wrapper = mountModal()
    await flushPromises()
    const dialog = wrapper.find('[role="dialog"]').element as HTMLElement
    const focusables = getFocusables(dialog)
    expect(focusables.length).toBeGreaterThanOrEqual(2)

    const first = focusables[0]
    const last = focusables[focusables.length - 1]
    first.focus()
    expect(document.activeElement).toBe(first)

    const event = dispatchTab(dialog, true)
    expect(event.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(last)
    wrapper.unmount()
  })

  it('Tab on the last focusable wraps focus to the first', async () => {
    const wrapper = mountModal()
    await flushPromises()
    const dialog = wrapper.find('[role="dialog"]').element as HTMLElement
    const focusables = getFocusables(dialog)
    const first = focusables[0]
    const last = focusables[focusables.length - 1]
    last.focus()
    expect(document.activeElement).toBe(last)

    const event = dispatchTab(dialog, false)
    expect(event.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(first)
    wrapper.unmount()
  })

  it('Tab on a middle focusable uses browser default (no preventDefault)', async () => {
    const wrapper = mountModal()
    await flushPromises()
    const dialog = wrapper.find('[role="dialog"]').element as HTMLElement
    const focusables = getFocusables(dialog)
    // A middle element must exist: close-btn, body-btn, cancel, confirm
    expect(focusables.length).toBeGreaterThanOrEqual(3)
    const middle = focusables[1]
    middle.focus()

    const forward = dispatchTab(dialog, false)
    expect(forward.defaultPrevented).toBe(false)

    const backward = dispatchTab(dialog, true)
    expect(backward.defaultPrevented).toBe(false)
    wrapper.unmount()
  })

  it('does NOT bounce focus back when a focusable outside the dialog is clicked', async () => {
    // Regression test for the focusin snap-back that PR #4980 introduced.
    const outside = document.createElement('button')
    outside.textContent = 'Outside'
    outside.id = 'outside-btn'
    document.body.appendChild(outside)

    const wrapper = mountModal()
    await flushPromises()

    outside.focus()
    // Give the browser a tick, then assert focus stayed on the outside button.
    await flushPromises()
    expect(document.activeElement).toBe(outside)
    wrapper.unmount()
    outside.remove()
  })
})


describe('BaseModal custom width prop (#10882)', () => {
  const mountWithProps = (props: Record<string, unknown>) =>
    mount(BaseModal, {
      props: { modelValue: true, title: 'Test', ...props },
      slots: { default: '<div>body</div>' },
      global: {
        plugins: [i18n],
        stubs: { Teleport: true, Transition: false, Icon: true },
      },
      attachTo: document.body,
    })

  it('applies a numeric width as an inline pixel max-width, overriding size', async () => {
    const wrapper = mountWithProps({ size: 'sm', width: 640 })
    await flushPromises()
    const dialog = wrapper.find('.aui-dialog')
    // size class stays (default preset behaviour preserved) ...
    expect(dialog.classes()).toContain('aui-dialog-sm')
    // ... but the explicit width wins via inline style
    expect(dialog.attributes('style') || '').toContain('max-width: 640px')
    wrapper.unmount()
  })

  it('passes a string width through unchanged', async () => {
    const wrapper = mountWithProps({ width: '42rem' })
    await flushPromises()
    const dialog = wrapper.find('.aui-dialog')
    expect(dialog.attributes('style') || '').toContain('max-width: 42rem')
    wrapper.unmount()
  })

  it('adds no inline max-width when width is absent (size preset governs)', async () => {
    const wrapper = mountWithProps({ size: 'lg' })
    await flushPromises()
    const dialog = wrapper.find('.aui-dialog')
    expect(dialog.classes()).toContain('aui-dialog-lg')
    expect(dialog.attributes('style') || '').not.toContain('max-width')
    wrapper.unmount()
  })
})
