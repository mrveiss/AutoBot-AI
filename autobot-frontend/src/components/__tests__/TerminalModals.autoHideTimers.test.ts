// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #16315: TerminalModals auto-hid its connection/command/kill/workflow
// messages with bare `setTimeout` calls that were never cleared - they fired
// after unmount (writing to a ref that was no longer rendered), and a fresh
// message never cancelled an older message's still-pending timer in the same
// slot. This proves both are fixed: the timer is cleared on unmount, and a
// second message in the same slot replaces the first slot's timer instead of
// racing it.

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import TerminalModals from '../terminal/TerminalModals.vue'

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages: { en: {} },
  missingWarn: false,
  fallbackWarn: false,
})

// BaseModal (@autobot/ui) wraps its body/actions in <Teleport to="body">;
// stub Teleport so the rendered message + buttons stay reachable via wrapper.find().
const mountOpts = {
  props: {
    showReconnectModal: true,
    showCommandConfirmation: false,
    showKillConfirmation: false,
    showLegacyModal: false,
    pendingCommand: '',
    pendingCommandRisk: 'low',
    pendingCommandReasons: [],
    runningProcesses: [],
    pendingWorkflowStep: null,
  },
  global: { plugins: [i18n], stubs: { teleport: true } },
}

// Reconnect is the 2nd button in the modal's actions row (Cancel, Reconnect).
const reconnectButton = (wrapper: VueWrapper) =>
  wrapper.findAll('.aui-dialog-actions button')[1]

const successText = (wrapper: VueWrapper) => wrapper.find('.success-text')

describe('TerminalModals auto-hide timers (#16315)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('clears the pending auto-hide timer on unmount', async () => {
    const wrapper = mount(TerminalModals, mountOpts)

    await reconnectButton(wrapper).trigger('click')
    // The reconnect simulation resolves after 1s, which is when handleSuccess
    // schedules the connection slot's 5s auto-hide timer.
    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()

    expect(successText(wrapper).text()).toBe('Successfully reconnected to terminal')

    // A second, unrelated timer (the reconnect action's own timeout guard,
    // filed separately as #16395) is also still pending here - that one is
    // out of scope for this fix, so assert the DELTA unmount produces rather
    // than an absolute vi.getTimerCount() of 0.
    const pendingBeforeUnmount = vi.getTimerCount()
    wrapper.unmount()

    expect(vi.getTimerCount()).toBe(pendingBeforeUnmount - 1)

    // Advancing past the original 5s window after unmount must not resurrect
    // the timer (it stays cleared) and must not throw.
    await vi.advanceTimersByTimeAsync(5000)
    expect(vi.getTimerCount()).toBe(pendingBeforeUnmount - 1)
  })

  it('a newer message in the same slot cancels the older one\'s timer, so it stays visible for its own full duration', async () => {
    const wrapper = mount(TerminalModals, mountOpts)

    // First message in the "connection" slot: shown at t=1000, would
    // auto-hide at t=6000 if nothing replaced it.
    await reconnectButton(wrapper).trigger('click')
    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()
    expect(successText(wrapper).exists()).toBe(true)

    // Second message in the same slot, shown at t=2000 (the button
    // re-enables once the first call's `finally` runs). This must cancel the
    // first message's timer rather than let it fire.
    await reconnectButton(wrapper).trigger('click')
    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()
    expect(successText(wrapper).exists()).toBe(true)

    // t=6000: the FIRST message's original timer would have fired here.
    // With the fix it was cancelled, so the (newer) message is still shown.
    await vi.advanceTimersByTimeAsync(4000)
    await flushPromises()
    expect(successText(wrapper).exists()).toBe(true)

    // t=7000: the SECOND message's own 5s window (started at t=2000) elapses.
    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()
    expect(successText(wrapper).exists()).toBe(false)
  })
})
