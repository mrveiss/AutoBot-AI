// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// #14777 AC4: keyboard behaviour of the kit BaseModal, verified on one migrated SLM dialog of
// each pattern -- confirm (RestartConfirmDialog), form (ScheduleModal) and viewer
// (ServiceLogsModal, which a parent mounts with v-if rather than toggling a flag). Each must
// trap Tab inside the dialog, close on Escape and hand focus back to the element that opened it.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import type { Component } from 'vue'
import en from '@/locales/en.json'
import RestartConfirmDialog from '@/components/orchestration/RestartConfirmDialog.vue'
import ScheduleModal from '@/components/ScheduleModal.vue'
import ServiceLogsModal from '@/components/fleet/ServiceLogsModal.vue'

vi.mock('@/composables/useSlmApi', () => ({
  useSlmApi: () => ({ getServiceLogs: vi.fn(async () => ({ logs: 'journal line' })) }),
}))

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

const FOCUSABLE =
  'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])'

interface Pattern {
  name: string
  component: Component
  closed: Record<string, unknown>
  open: Record<string, unknown>
  closeEvent: string
}

const PATTERNS: Pattern[] = [
  {
    name: 'confirm: RestartConfirmDialog',
    component: RestartConfirmDialog,
    closed: { show: false, message: 'Restart <b>redis</b>?' },
    open: { show: true },
    closeEvent: 'cancel',
  },
  {
    name: 'form: ScheduleModal',
    component: ScheduleModal,
    closed: { show: false },
    open: { show: true },
    closeEvent: 'close',
  },
  {
    name: 'viewer: ServiceLogsModal',
    component: ServiceLogsModal,
    closed: { nodeId: 'node-1', serviceName: null },
    open: { serviceName: 'redis' },
    closeEvent: 'close',
  },
]

function pressTab(el: Element, shiftKey: boolean): KeyboardEvent {
  const event = new KeyboardEvent('keydown', { key: 'Tab', shiftKey, bubbles: true, cancelable: true })
  el.dispatchEvent(event)
  return event
}

describe.each(PATTERNS)('modal keyboard behaviour -- $name', (pattern) => {
  let wrapper: VueWrapper | undefined
  let opener: HTMLButtonElement
  const openers: HTMLButtonElement[] = []

  /** Mount closed, focus an opener button, open the dialog, and give the dialog its focus. */
  async function openFromOpener(): Promise<HTMLElement> {
    opener = document.createElement('button')
    opener.textContent = 'Open'
    document.body.appendChild(opener)
    openers.push(opener)
    opener.focus()
    wrapper = mount(pattern.component, {
      props: pattern.closed,
      global: { plugins: [i18n], stubs: { Teleport: true, Transition: false } },
      attachTo: document.body,
    })
    await flushPromises()
    await wrapper.setProps(pattern.open)
    await flushPromises()
    const dialog = wrapper.find('[role="dialog"]').element as HTMLElement
    dialog.querySelectorAll<HTMLElement>(FOCUSABLE)[0].focus()
    return dialog
  }

  /** Close the way a parent does: apply what the dialog asked for. */
  async function closeLikeParent(): Promise<void> {
    await wrapper!.setProps(pattern.closed)
    await flushPromises()
  }

  beforeEach(() => {
    document.body.replaceChildren()
    vi.stubGlobal('fetch', vi.fn(async () => new Response('[]', { status: 200, headers: { 'content-type': 'application/json' } })))
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = undefined
    openers.splice(0).forEach((el) => el.remove())
    vi.unstubAllGlobals()
  })

  it('traps Tab and Shift+Tab inside the dialog', async () => {
    const dialog = await openFromOpener()
    const focusables = Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE))
    expect(focusables.length).toBeGreaterThanOrEqual(2)
    const first = focusables[0]
    const last = focusables[focusables.length - 1]

    last.focus()
    expect(pressTab(last, false).defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(first)

    expect(pressTab(first, true).defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(last)
    expect(dialog.contains(document.activeElement)).toBe(true)
  })

  it('asks to close on Escape', async () => {
    const dialog = await openFromOpener()
    const target = document.activeElement as HTMLElement
    expect(dialog.contains(target)).toBe(true)
    target.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }))
    await flushPromises()
    expect(wrapper!.emitted(pattern.closeEvent)).toHaveLength(1)
  })

  it('returns focus to the opener once closed', async () => {
    const dialog = await openFromOpener()
    expect(dialog.contains(document.activeElement)).toBe(true)
    expect(document.activeElement).not.toBe(opener)

    ;(document.activeElement as HTMLElement).dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }),
    )
    await closeLikeParent()

    expect(wrapper!.find('[role="dialog"]').exists()).toBe(false)
    expect(document.activeElement).toBe(opener)
  })
})

// RestartConfirmDialog passes :locked="isProcessing": while a restart runs the dialog cannot be
// dismissed, and focus must not leave it.
describe('modal keyboard behaviour -- locked: RestartConfirmDialog while processing', () => {
  let wrapper: VueWrapper | undefined

  afterEach(() => {
    wrapper?.unmount()
    wrapper = undefined
    document.body.replaceChildren()
  })

  it('ignores Escape and keeps focus inside the dialog', async () => {
    wrapper = mount(RestartConfirmDialog, {
      props: { show: true, message: 'Restart redis?', isProcessing: true },
      global: { plugins: [i18n], stubs: { Teleport: true, Transition: false } },
      attachTo: document.body,
    })
    await flushPromises()
    const dialog = wrapper.find('[role="dialog"]').element as HTMLElement
    dialog.setAttribute('tabindex', '-1')
    dialog.focus()
    dialog.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }))
    await flushPromises()
    expect(wrapper.emitted('cancel')).toBeUndefined()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    expect(dialog.contains(document.activeElement)).toBe(true)
  })
})
