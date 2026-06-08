// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * HostSelectionDialog focus-trap tests (#5016)
 *
 * Regression coverage for the Tab / Shift+Tab wrap that replaces the old
 * focusin snap-to-first-element pattern which broke keyboard wrap and
 * bounced focus back whenever a user clicked anything outside the dialog.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import HostSelectionDialog from '../HostSelectionDialog.vue'

vi.mock('@/utils/SecretsApiClient', () => ({
  secretsApiClient: {
    getSecrets: vi.fn().mockResolvedValue({ secrets: [] }),
  },
}))

vi.mock('@/config/ssot-config', () => ({
  getBackendUrl: () => 'http://localhost:8001',
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ info: vi.fn(), error: vi.fn(), warn: vi.fn(), debug: vi.fn() }),
}))

// Stub fetch to return one legacy host so the dialog has multiple focusables.
beforeEach(() => {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      hosts: [
        { id: 'h1', name: 'Host One', host: '10.0.0.1', ssh_port: 22, username: 'root' },
        { id: 'h2', name: 'Host Two', host: '10.0.0.2', ssh_port: 22, username: 'root' },
      ],
    }),
  }) as unknown as typeof fetch
  document.body.replaceChildren()
})

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      ui: {
        hostSelection: {
          title: 'Host',
          defaultPurpose: 'Choose',
          close: 'Close',
          commandToExecute: 'Run',
          availableHosts: 'Hosts',
          loadingHosts: 'Loading',
          noHostsConfigured: 'None',
          addHost: 'Add',
          default: 'Default',
          setAsDefault: 'Make default',
          rememberChoice: 'Remember',
          cancel: 'Cancel',
          connecting: 'Connecting',
          connectAndExecute: 'Connect',
          securityNote: 'Secure',
          pleaseSelectHost: 'Pick one',
          hostNotFound: 'Missing',
          failedToLoadHosts: 'Load failed',
          failedToConnect: 'Connect failed',
        },
      },
    },
  },
})

const mountDialog = () =>
  mount(HostSelectionDialog, {
    props: { show: true, command: 'echo hi', purpose: 'test' },
    global: { plugins: [i18n] },
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

describe('HostSelectionDialog focus trap (#5016)', () => {
  it('renders with loaded hosts producing multiple focusable controls', async () => {
    const wrapper = mountDialog()
    await flushPromises()
    await flushPromises()
    const dialog = wrapper.find('[role="dialog"]').element as HTMLElement
    const focusables = getFocusables(dialog)
    expect(focusables.length).toBeGreaterThanOrEqual(3)
    wrapper.unmount()
  })

  it('Shift+Tab on the first focusable wraps to the last', async () => {
    const wrapper = mountDialog()
    await flushPromises()
    await flushPromises()
    const dialog = wrapper.find('[role="dialog"]').element as HTMLElement
    const focusables = getFocusables(dialog)
    const first = focusables[0]
    const last = focusables[focusables.length - 1]
    first.focus()
    expect(document.activeElement).toBe(first)

    const event = dispatchTab(dialog, true)
    expect(event.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(last)
    wrapper.unmount()
  })

  it('Tab on the last focusable wraps to the first', async () => {
    const wrapper = mountDialog()
    await flushPromises()
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

  it('Tab on a middle focusable does not preventDefault', async () => {
    const wrapper = mountDialog()
    await flushPromises()
    await flushPromises()
    const dialog = wrapper.find('[role="dialog"]').element as HTMLElement
    const focusables = getFocusables(dialog)
    expect(focusables.length).toBeGreaterThanOrEqual(3)
    const middle = focusables[1]
    middle.focus()

    const forward = dispatchTab(dialog, false)
    expect(forward.defaultPrevented).toBe(false)

    const backward = dispatchTab(dialog, true)
    expect(backward.defaultPrevented).toBe(false)
    wrapper.unmount()
  })

  it('does NOT bounce focus back when a button outside the dialog is focused', async () => {
    // Regression: old focusin listener would yank focus back to focusable[0]
    // any time an outside element gained focus.
    const outside = document.createElement('button')
    outside.textContent = 'Outside'
    document.body.appendChild(outside)

    const wrapper = mountDialog()
    await flushPromises()
    await flushPromises()

    outside.focus()
    await flushPromises()
    expect(document.activeElement).toBe(outside)
    wrapper.unmount()
    outside.remove()
  })
})
