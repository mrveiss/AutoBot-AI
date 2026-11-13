// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BaseModal's initial focus and its real Teleport path (#21179). A sibling of BaseModal.test.ts,
// which stubs both Teleport and the enter transition and so can reach neither:
//
//  * Initial focus is moved from the Transition's `after-enter` hook. Vue Test Utils stubs
//    <Transition> by default, and the hook never fires on a stub; here the real Transition runs
//    (`stubs: { transition: false }`), so the hook is awaited rather than skipped. jsdom has no CSS
//    durations, so the transition ends on the next animation frames: assertions wait for the focus
//    with `vi.waitFor` instead of guessing a number of ticks.
//  * The shipped component renders its dialog through `<Teleport to="body">`. With Teleport left
//    unstubbed the dialog is NOT inside the wrapper; it is queried from `document.body`, as a user
//    of the app reaches it.
//
// These live beside BaseModal.test.ts, not in it: adding them there would take that file past the
// 600-line limit of the frontend file-size guard.

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import BaseModal from '../BaseModal.vue'

const BODY_SLOTS = {
  default: '<button class="body-btn">Body</button>',
  actions: '<button class="cancel">Cancel</button><button class="confirm">OK</button>',
}

const FOCUSABLE =
  'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])'

let wrapper: VueWrapper | undefined
let opener: HTMLButtonElement

/** Mount closed with an opener focused, real Transition, Teleport real unless `stubTeleport`. */
function mountClosed(
  props: Record<string, unknown> = {},
  slots: Record<string, string> = BODY_SLOTS,
  stubTeleport = false,
): VueWrapper {
  opener = document.createElement('button')
  opener.textContent = 'Open'
  document.body.appendChild(opener)
  opener.focus()
  wrapper = mount(BaseModal, {
    props: { modelValue: false, title: 'Dialog title', ...props },
    slots,
    global: { stubs: { transition: false, ...(stubTeleport ? { Teleport: true } : {}) } },
    attachTo: document.body,
  })
  return wrapper
}

const dialogEl = () => document.body.querySelector<HTMLElement>('[role="dialog"]')
const closeButton = () => document.body.querySelector<HTMLElement>('.aui-dialog-close')

/** The focus lands once the enter transition has ended; before that it is still on the opener. */
async function openAndWaitForFocus(target: () => Element | null): Promise<void> {
  await wrapper!.setProps({ modelValue: true })
  expect(document.activeElement).toBe(opener)
  await vi.waitFor(() => expect(document.activeElement).toBe(target()))
}

beforeEach(() => {
  document.body.replaceChildren()
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  document.body.replaceChildren()
})

describe('BaseModal initial focus (#21179)', () => {
  it('moves focus to the first focusable, the close button, once the enter transition ends', async () => {
    // fails if onAfterEnter stops calling focusFirst, or the hook is dropped from the Transition
    mountClosed()
    await openAndWaitForFocus(closeButton)
  })

  it('focuses the first body control when there is no close button', async () => {
    // the first focusable is whatever comes first in the dialog, not always the close button
    mountClosed({ showClose: false })
    await openAndWaitForFocus(() => document.body.querySelector('.body-btn'))
  })

  it('focuses the first body control of a locked dialog, which has no close button', async () => {
    mountClosed({ locked: true })
    await openAndWaitForFocus(() => document.body.querySelector('.body-btn'))
    expect(closeButton()).toBeNull()
  })

  it('falls back to the dialog itself when nothing inside it is focusable', async () => {
    mountClosed({ showClose: false }, { default: '<p>Read only</p>' })
    await openAndWaitForFocus(dialogEl)
  })

  it('also focuses a dialog mounted already open, since the Transition appears', async () => {
    // fails if `appear` is removed: a v-if'd modal never runs an enter transition on first render
    opener = document.createElement('button')
    document.body.appendChild(opener)
    opener.focus()
    wrapper = mount(BaseModal, {
      props: { modelValue: true, title: 'Dialog title' },
      slots: BODY_SLOTS,
      global: { stubs: { transition: false } },
      attachTo: document.body,
    })
    await vi.waitFor(() => expect(document.activeElement).toBe(closeButton()))
  })
})

describe('BaseModal with the real Teleport (#21179)', () => {
  async function openDialog(): Promise<HTMLElement> {
    mountClosed()
    await wrapper!.setProps({ modelValue: true })
    await vi.waitFor(() => expect(dialogEl()).not.toBeNull())
    return dialogEl()!
  }

  it('renders the dialog under document.body, outside the wrapper', async () => {
    // fails if `to="body"` is changed or the Teleport is removed
    const dialog = await openDialog()
    expect(wrapper!.find('[role="dialog"]').exists()).toBe(false)
    expect(dialog.getAttribute('aria-modal')).toBe('true')
    expect(dialog.parentElement?.parentElement).toBe(document.body)
    expect(dialog.querySelector('.body-btn')).not.toBeNull()
  })

  it('traps Tab and Shift+Tab inside the teleported dialog', async () => {
    // fails if the trap's keydown handler is not on the dialog element that moved to <body>
    const dialog = await openDialog()
    const focusables = Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE))
    expect(focusables.length).toBeGreaterThanOrEqual(2)
    const first = focusables[0]
    const last = focusables[focusables.length - 1]

    last.focus()
    const forward = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true })
    last.dispatchEvent(forward)
    expect(forward.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(first)

    const backward = new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true, cancelable: true })
    first.dispatchEvent(backward)
    expect(backward.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(last)
  })

  it('asks to close on Escape pressed inside the teleported dialog', async () => {
    const dialog = await openDialog()
    dialog.querySelector<HTMLElement>('.body-btn')!.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }),
    )
    expect(wrapper!.emitted('close')).toHaveLength(1)
    expect(wrapper!.emitted('update:modelValue')).toEqual([[false]])
  })

  it('returns focus to the opener once it has closed and left the document', async () => {
    // fails if useFocusRestore is unwired,
    const dialog = await openDialog()
    dialog.querySelector<HTMLElement>('.body-btn')!.focus()
    expect(document.activeElement).not.toBe(opener)

    await wrapper!.setProps({ modelValue: false })
    await vi.waitFor(() => expect(dialogEl()).toBeNull())
    await vi.waitFor(() => expect(document.activeElement).toBe(opener))
  })
})
