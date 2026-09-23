// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Issue #15825 — a FAILED provision rendered no control at all.
 *
 * The Continue button was gated on `provisionComplete` (`status === 'completed'`),
 * and the status bar and phase chips on `provisioning || provisionComplete`.
 * Failure is neither, so the panel showed a heading, a paragraph, and nothing
 * else: no error, no phases, no button, no way forward or back.
 *
 * That is why the underlying provisioning defect (#15822) reached the user as
 * "cannot get past step 7" rather than "provisioning failed, here is the
 * error" — and it cost real diagnosis time before anyone looked at ansible.
 *
 * The store had carried `isFailed` and `error` all along. Nothing read them.
 *
 * **Why this mounts the component instead of reading the template.** The
 * failure branch is a rendering decision, and the pre-fix template *contained*
 * a Continue button and a status bar — so any assertion of the form "the
 * template has a button" passed while the dead end was live. Only rendering in
 * the failed state distinguishes the two.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createPinia, setActivePinia } from 'pinia'
import { ref, computed, reactive } from 'vue'
import en from '@/locales/en.json'

// Mirrors every member SetupWizardView actually reads off the store. A member
// missing here is not a soft failure: `restoreFromBackend` and `disconnectWs`
// are lifecycle calls, so an omission throws during mount and fails all of
// these tests for a reason unrelated to what they assert.
const provisionState = {
  status: ref<'idle' | 'running' | 'completed' | 'failed'>('failed'),
  error: ref<string | null>('ansible aborted in play 1'),
  logs: ref<string[]>([]),
  stage: ref<string | null>('provision'),
  startedAt: ref<number | null>(null),
  elapsedSeconds: ref(0),
  currentTask: ref(''),
  currentPhase: ref(''),
  completedPhases: ref<Set<string>>(new Set<string>()),
}

// `reactive` rather than a plain object: a Pinia store unwraps refs on property
// access, so the component reads `provisionStore.stage` as a string. A plain
// object hands back the Ref itself and `stage.replace` throws -- which is a
// mock-shaped failure, not a finding about the component.
vi.mock('@/stores/provision', () => ({
  useProvisionStore: () => reactive({
    status: provisionState.status,
    error: provisionState.error,
    logs: provisionState.logs,
    stage: provisionState.stage,
    startedAt: provisionState.startedAt,
    elapsedSeconds: provisionState.elapsedSeconds,
    currentTask: provisionState.currentTask,
    currentPhase: provisionState.currentPhase,
    completedPhases: provisionState.completedPhases,
    isRunning: computed(() => provisionState.status.value === 'running'),
    isComplete: computed(() => provisionState.status.value === 'completed'),
    isFailed: computed(() => provisionState.status.value === 'failed'),
    start: vi.fn(),
    restoreFromBackend: vi.fn().mockResolvedValue(undefined),
    connectWs: vi.fn(),
    disconnectWs: vi.fn(),
    reset: vi.fn(),
  }),
}))

const provisionWizardFleet = vi.fn().mockResolvedValue(undefined)

vi.mock('@/composables/useSlmApi', () => ({
  useSlmApi: () => ({
    getNodes: vi.fn().mockResolvedValue([]),
    getRoles: vi.fn().mockResolvedValue([]),
    registerNode: vi.fn(),
    testConnection: vi.fn(),
    enrollNode: vi.fn(),
    updateNodeRoles: vi.fn(),
    upsertSecret: vi.fn(),
    getSecretValue: vi.fn(),
    getWizardStatus: vi.fn().mockResolvedValue({ current_step: 'provision_fleet', completed_steps: [] }),
    completeWizardStep: vi.fn().mockResolvedValue(undefined),
    skipWizardSetup: vi.fn(),
    provisionWizardFleet,
    validateWizardFleet: vi.fn().mockResolvedValue({}),
  }),
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ showToast: vi.fn(), success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {}, params: {} }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

import SetupWizardView from './SetupWizardView.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

async function mountOnProvisionStep() {
  const wrapper = mount(SetupWizardView, { global: { plugins: [i18n] } })
  // The step is local state; the wizard resolves it from getWizardStatus on
  // mount, but setting it directly keeps this test about the failure branch
  // rather than about step navigation.
  ;(wrapper.vm as unknown as { currentStep: string }).currentStep = 'provision_fleet'
  await wrapper.vm.$nextTick()
  return wrapper
}

describe('SetupWizardView — a failed provision (#15825)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    provisionState.status.value = 'failed'
    provisionState.error.value = 'ansible aborted in play 1'
  })

  it('offers a control instead of a dead end', async () => {
    const wrapper = await mountOnProvisionStep()

    const failure = wrapper.find('.provision-failure')
    expect(failure.exists()).toBe(true)
    expect(failure.findAll('button').length).toBeGreaterThan(0)
  })

  it('actually retries when the control is clicked', async () => {
    // "There is a button" is satisfiable by a button wired to nothing. A
    // removed or misdirected click handler passes the assertion above and
    // leaves the user on the same dead end, one click further in.
    const wrapper = await mountOnProvisionStep()
    provisionWizardFleet.mockClear()

    await wrapper.find('.provision-failure button').trigger('click')

    expect(provisionWizardFleet).toHaveBeenCalled()
  })

  it('says that provisioning failed, rather than showing nothing', async () => {
    const wrapper = await mountOnProvisionStep()

    expect(wrapper.text()).toContain(en.setupWizardView.provisioningFailed)
  })

  it("surfaces the store's error text, which nothing read before", async () => {
    const wrapper = await mountOnProvisionStep()

    expect(wrapper.text()).toContain('ansible aborted in play 1')
  })

  it('keeps the phase chips visible so the failing phase is identifiable', async () => {
    const wrapper = await mountOnProvisionStep()

    // Gated on `provisioning || provisionComplete` before the fix, so the
    // phases vanished at exactly the moment they became diagnostic.
    expect(wrapper.find('.provision-phases').exists()).toBe(true)
  })

  it('shows no failure panel on a successful provision', async () => {
    // The contrast case. Without it, a panel rendered unconditionally would
    // satisfy every assertion above while telling a user that a successful
    // install had failed.
    provisionState.status.value = 'completed'
    provisionState.error.value = null

    const wrapper = await mountOnProvisionStep()

    expect(wrapper.find('.provision-failure').exists()).toBe(false)
    expect(wrapper.text()).toContain(en.setupWizardView.continue)
  })
})
