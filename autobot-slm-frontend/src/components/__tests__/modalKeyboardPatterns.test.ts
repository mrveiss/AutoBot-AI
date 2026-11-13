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
import RoleManagementModal from '@/components/RoleManagementModal.vue'

vi.mock('@/composables/useSlmApi', () => ({
  useSlmApi: () => ({ getServiceLogs: vi.fn(async () => ({ logs: 'journal line' })) }),
}))

// RoleManagementModal reads its roles through useRoles; one manual role gives it a Remove button.
vi.mock('@/composables/useRoles', () => ({
  useRoles: () => ({
    roles: [],
    fetchRoles: vi.fn(async () => undefined),
    getNodeRoles: vi.fn(async () => ({
      node_id: 'node-1',
      detected_roles: [],
      role_versions: {},
      listening_ports: [],
      roles: [
        {
          role_name: 'redis',
          assignment_type: 'manual',
          status: 'active',
          current_version: null,
          last_synced_at: null,
          last_error: null,
        },
      ],
    })),
    assignRole: vi.fn(),
    removeRole: vi.fn(),
    syncRole: vi.fn(),
  }),
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

// RoleManagementModal's Remove confirmation sits on top of the role dialog (#14777). It is a dialog
// of its own, so it traps focus, closes on Escape WITHOUT closing the role dialog behind it, and
// hands focus back to the Remove button. Teleport is real here: the two dialogs are siblings under
// <body> as in the app, not nested in the DOM, so the role dialog's key handlers never see the
// confirm's keys.
describe('modal keyboard behaviour -- nested confirm: RoleManagementModal remove', () => {
  let wrapper: VueWrapper | undefined

  const dialogs = () => Array.from(document.body.querySelectorAll<HTMLElement>('[role="dialog"]'))
  const press = (el: Element, init: KeyboardEventInit) =>
    el.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...init }))

  /** Open the role dialog, focus its Remove button and click it; returns the button and the confirm. */
  async function openConfirm(): Promise<{ removeButton: HTMLElement; confirm: HTMLElement }> {
    wrapper = mount(RoleManagementModal, {
      props: { nodeId: 'node-1', hostname: 'host-1' },
      global: { plugins: [i18n], stubs: { Transition: false } },
      attachTo: document.body,
    })
    await flushPromises()
    const removeButton = document.body.querySelector<HTMLElement>(
      `[aria-label="${en.roleManagementModal.removeRoleAria.replace('{roleName}', 'redis')}"]`,
    )!
    expect(dialogs()).toHaveLength(1)
    removeButton.focus()
    removeButton.click()
    await flushPromises()
    expect(dialogs()).toHaveLength(2)
    const confirm = dialogs()[1]
    confirm.querySelectorAll<HTMLElement>(FOCUSABLE)[0].focus()
    return { removeButton, confirm }
  }

  beforeEach(() => {
    document.body.replaceChildren()
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = undefined
    document.body.replaceChildren()
  })

  it('is a dialog of its own, named by the question it asks', async () => {
    const { confirm } = await openConfirm()
    expect(confirm.getAttribute('aria-modal')).toBe('true')
    const label = document.getElementById(confirm.getAttribute('aria-labelledby')!)
    expect(label?.textContent).toContain(en.roleManagementModal.removeValue0.replace('{value0}', 'redis'))
  })

  it('traps Tab and Shift+Tab inside the confirm', async () => {
    const { confirm } = await openConfirm()
    const focusables = Array.from(confirm.querySelectorAll<HTMLElement>(FOCUSABLE))
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

  it('closes only the confirm on Escape and gives focus back to the Remove button', async () => {
    const { removeButton, confirm } = await openConfirm()
    expect(confirm.contains(document.activeElement)).toBe(true)

    press(document.activeElement!, { key: 'Escape' })
    await flushPromises()

    // The confirm leaves through its transition, so wait for it rather than for one tick.
    await vi.waitFor(() => expect(dialogs()).toHaveLength(1))
    expect(wrapper!.emitted('close')).toBeUndefined()
    await vi.waitFor(() => expect(document.activeElement).toBe(removeButton))
  })
})
