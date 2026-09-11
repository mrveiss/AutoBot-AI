// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * TerminalModals reports the parent's real outcome for each action, never a
 * success after a fixed delay (#16285).
 */

import { describe, it, expect, afterEach, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import TerminalModals from '../terminal/TerminalModals.vue'
import en from '@/i18n/locales/en.json'

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() }),
}))

type ModalsProps = InstanceType<typeof TerminalModals>['$props']

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const modals = en.terminal.modals

// Renders the dialog body and its actions whenever the modal is open.
const BaseModalStub = {
  props: ['modelValue'],
  template: '<div v-if="modelValue"><slot /><slot name="actions" /></div>',
}

const ok = () => Promise.resolve()

function mountModals(props: Partial<ModalsProps>) {
  return mount(TerminalModals, {
    props: {
      showReconnectModal: false,
      showCommandConfirmation: false,
      showKillConfirmation: false,
      showLegacyModal: false,
      pendingCommand: 'rm -rf build',
      pendingCommandRisk: 'high',
      pendingCommandReasons: [],
      runningProcesses: [{ pid: 1, command: 'sleep 60' }],
      pendingWorkflowStep: { stepNumber: 1, totalSteps: 2, command: 'ls', description: 'List files' },
      reconnectAction: ok,
      executeCommandAction: ok,
      emergencyKillAction: ok,
      confirmStepAction: ok,
      skipStepAction: ok,
      manualControlAction: ok,
      ...props,
    },
    global: { plugins: [i18n], stubs: { BaseModal: BaseModalStub } },
  })
}

async function press(wrapper: VueWrapper, label: string) {
  const button = wrapper.findAll('button').find((candidate) => candidate.text().includes(label))
  if (!button) throw new Error(`no button labelled "${label}"`)
  await button.trigger('click')
  await flushPromises()
}

const errorText = (wrapper: VueWrapper) => wrapper.find('.error-text')
const successText = (wrapper: VueWrapper) => wrapper.find('.success-text')

describe('TerminalModals (#16285)', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it("shows the error when the parent's action rejects, and reports no success", async () => {
    const wrapper = mountModals({
      showCommandConfirmation: true,
      executeCommandAction: () => Promise.reject(new Error('permission denied')),
    })

    await press(wrapper, modals.executeCommand)

    expect(errorText(wrapper).text()).toBe('permission denied')
    expect(successText(wrapper).exists()).toBe(false)
  })

  it("shows the error when the parent's action throws synchronously", async () => {
    const wrapper = mountModals({
      showKillConfirmation: true,
      emergencyKillAction: () => {
        throw new Error('no such session')
      },
    })

    await press(wrapper, modals.killAll)

    expect(errorText(wrapper).text()).toBe('no such session')
    expect(successText(wrapper).exists()).toBe(false)
  })

  it('reports success only once the action settles, with no fixed delay', async () => {
    let settle: () => void = () => {}
    const wrapper = mountModals({
      showReconnectModal: true,
      reconnectAction: () =>
        new Promise<void>((resolve) => {
          settle = resolve
        }),
    })

    await press(wrapper, en.terminal.reconnect)
    expect(successText(wrapper).exists()).toBe(false)

    settle()
    await flushPromises()

    expect(successText(wrapper).text()).toBe(modals.reconnectSucceeded)
  })

  it('fails the action at its deadline when the parent never settles', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    const wrapper = mountModals({
      showCommandConfirmation: true,
      executeCommandAction: () => new Promise(() => {}),
    })

    await press(wrapper, modals.executeCommand)
    await vi.advanceTimersByTimeAsync(30_000)
    await flushPromises()

    expect(errorText(wrapper).text()).toBe(modals.commandTimedOut)
    expect(successText(wrapper).exists()).toBe(false)
  })

  it('shows a workflow-step failure in the step modal', async () => {
    const wrapper = mountModals({
      showLegacyModal: true,
      skipStepAction: () => Promise.reject(new Error('step already ran')),
    })

    await press(wrapper, modals.skipStep)

    expect(errorText(wrapper).text()).toBe('step already ran')
    expect(successText(wrapper).exists()).toBe(false)
  })

  it('reports manual control once the parent has taken it', async () => {
    const manualControlAction = vi.fn(() => Promise.resolve())
    const wrapper = mountModals({ showLegacyModal: true, manualControlAction })

    await press(wrapper, modals.takeManualControl)

    expect(manualControlAction).toHaveBeenCalledOnce()
    expect(successText(wrapper).text()).toBe(modals.manualControlTaken)
  })
})
