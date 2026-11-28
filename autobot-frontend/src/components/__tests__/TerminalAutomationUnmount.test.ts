// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * No automation-pacing callback fires after its component unmounts (#16396):
 * one mount/unmount case per component that paces workflow steps. The
 * composable's own contract is pinned in useAutomationPacing.test.ts; this file
 * proves each component's real unmount reaches it.
 *
 * Kept out of TerminalWindow.test.ts so that file does not grow.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref, reactive } from 'vue'
import { createI18n } from 'vue-i18n'
import TerminalWindow from '../terminal/TerminalWindow.vue'
import WorkflowAutomation from '../terminal/WorkflowAutomation.vue'
import { createTestRouter } from '../../test/utils/test-utils'
import { FIRST_STEP_DELAY_MS, NEXT_STEP_DELAY_MS, STEP_OFFER_DELAY_MS } from '@/composables/useAutomationPacing'

vi.mock('@/utils/ApiClient', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), patch: vi.fn() },
}))
vi.mock('@/services/TerminalService', () => ({
  useTerminalService: vi.fn(() => ({
    sendInput: vi.fn(),
    sendStdin: vi.fn(),
    sendTabCompletion: vi.fn(),
    sendHistoryGet: vi.fn(),
    sendHistorySearch: vi.fn(),
    sendSignal: vi.fn(),
    resize: vi.fn(),
    isConnected: vi.fn(() => false),
    sessions: reactive(new Map()),
    connectionStatus: ref('disconnected'),
    createSession: vi.fn().mockResolvedValue('test-session-id'),
    connect: vi.fn().mockResolvedValue(undefined),
    disconnect: vi.fn(),
    closeSession: vi.fn().mockResolvedValue(undefined),
  })),
}))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() }),
}))

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages: { en: {} },
  missingWarn: false,
  fallbackWarn: false,
})

const PAST_EVERY_DELAY = FIRST_STEP_DELAY_MS + NEXT_STEP_DELAY_MS + STEP_OFFER_DELAY_MS
const WORKFLOW = { name: 'w', steps: [{ command: 'ls' }, { command: 'pwd' }] }
const STEP = { stepNumber: 1, totalSteps: 1, command: 'ls' }

describe('automation pacing stops at unmount (#16396)', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('TerminalWindow: a started workflow dequeues nothing once unmounted', () => {
    const wrapper = mount(TerminalWindow, {
      global: {
        plugins: [i18n, createTestRouter(undefined, ['/terminal/test-session'])],
        stubs: {
          AdvancedStepConfirmationModal: { template: '<div />' },
          CompletionSuggestions: { template: '<div />' },
          TerminalModals: { template: '<div />' },
        },
      },
    })
    const vm = wrapper.vm as unknown as {
      startAutomatedWorkflow: (w: typeof WORKFLOW) => void
      automationQueue: unknown[]
      waitingForUserConfirmation: boolean
    }
    vm.startAutomatedWorkflow(WORKFLOW)
    expect(vm.automationQueue).toHaveLength(2)

    wrapper.unmount()
    vi.advanceTimersByTime(PAST_EVERY_DELAY)

    // Had the first-step timer survived, it would have shifted the queue and
    // offered step 1 for confirmation.
    expect(vm.automationQueue).toHaveLength(2)
    expect(vm.waitingForUserConfirmation).toBe(false)
  })

  it('WorkflowAutomation: a pending step offer never fires once unmounted', () => {
    const wrapper = mount(WorkflowAutomation, {
      props: {
        automationPaused: false,
        hasAutomatedWorkflow: true,
        currentWorkflowStep: 0,
        workflowSteps: [STEP],
        pendingWorkflowStep: null,
        automationQueue: [STEP],
        waitingForUserConfirmation: false,
      },
      global: { plugins: [i18n] },
    })
    ;(wrapper.vm as unknown as { executeAllRemainingSteps: () => void }).executeAllRemainingSteps()
    expect(vi.getTimerCount()).toBe(1)

    wrapper.unmount()

    expect(vi.getTimerCount()).toBe(0)
    vi.advanceTimersByTime(PAST_EVERY_DELAY)
    expect(wrapper.emitted('request-manual-step-confirmation')).toBeUndefined()
  })
})
