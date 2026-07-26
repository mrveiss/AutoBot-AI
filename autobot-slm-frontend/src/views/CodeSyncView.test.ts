// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Issue #12593 — Update-All stage 3 (`slm_self_update`) restarts the SLM
 * control plane the page itself polls. For the ~1min restart window the poller
 * only sees transient failures; previously the UI showed a bare "updating..."
 * spinner and read as frozen. These tests mount CodeSyncView and drive the poll
 * loop to prove the reconnecting affordance (inline notice + amber banner)
 * renders IMMEDIATELY for a stage-3 transient error, and does NOT render for a
 * non-stage-3 transient error.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { ref, computed } from 'vue'
import en from '@/locales/en.json'
import type { UpdateAllJob, UpdateAllStage } from '@/composables/useCodeSync'

// Controllable poll responses (swapped per-test).
let getUpdateAllStatusImpl: () => Promise<UpdateAllJob | null | undefined>
let startUpdateAllImpl: () => Promise<UpdateAllJob | null>

vi.mock('@/composables/useCodeSource', () => ({
  useCodeSource: () => ({
    codeSource: ref(null),
    fetchCodeSource: vi.fn().mockResolvedValue(undefined),
    removeCodeSource: vi.fn().mockResolvedValue(undefined),
  }),
}))

// Mock only useCodeSync(); keep the real pure helpers (isSelfUpdateReconnecting
// etc.) so the test exercises the actual view↔helper wiring.
vi.mock('@/composables/useCodeSync', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/composables/useCodeSync')>()
  return {
    ...actual,
    useCodeSync: () => ({
      loading: ref(false),
      error: ref(null),
      status: ref(null),
      pendingNodes: ref([]),
      schedules: ref([]),
      roles: ref([]),
      hasOutdatedNodes: computed(() => false),
      outdatedCount: computed(() => 0),
      totalNodes: computed(() => 0),
      latestVersion: ref(null),
      hasUpdate: ref(true), // renders the active "Update Everything" CTA
      fetchStatus: vi.fn().mockResolvedValue(undefined),
      fetchPendingNodes: vi.fn().mockResolvedValue(undefined),
      fetchSchedules: vi.fn().mockResolvedValue(undefined),
      fetchRoles: vi.fn().mockResolvedValue(undefined),
      fetchDrift: vi.fn(),
      getResolveDriftStatus: vi.fn(),
      startResolveDriftAsync: vi.fn(),
      selfUpdate: vi.fn(),
      pullFromSource: vi.fn(),
      refreshVersion: vi.fn().mockResolvedValue(undefined),
      syncFleet: vi.fn(),
      syncNode: vi.fn(),
      syncRole: vi.fn(),
      clearError: vi.fn(),
      setError: vi.fn(),
      createSchedule: vi.fn(),
      updateSchedule: vi.fn(),
      deleteSchedule: vi.fn(),
      toggleSchedule: vi.fn(),
      runSchedule: vi.fn(),
      startUpdateAll: () => startUpdateAllImpl(),
      getUpdateAllStatus: () => getUpdateAllStatusImpl(),
    }),
  }
})

import CodeSyncView from './CodeSyncView.vue'

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

function makeStage(name: string, status: UpdateAllStage['status']): UpdateAllStage {
  return {
    name,
    status,
    message: null,
    sha: null,
    deps_changed: false,
    log_lines: [],
    started_at: null,
    completed_at: null,
  }
}

function makeJob(runningStage: string): UpdateAllJob {
  return {
    job_id: 'job-ua',
    status: 'running',
    stages: [
      makeStage('github_fetch', 'success'),
      makeStage('code_source_pull', 'success'),
      makeStage('slm_self_update', runningStage === 'slm_self_update' ? 'running' : 'pending'),
      makeStage('fleet_nodes', runningStage === 'fleet_nodes' ? 'running' : 'pending'),
    ],
    total_fleet_nodes: 2,
    completed_fleet_nodes: 0,
    failed_fleet_nodes: 0,
    created_at: '2026-01-01T00:00:00Z',
    completed_at: null,
    failure_reason: null,
  }
}

async function mountAndStartWithTransientError(runningStage: string) {
  startUpdateAllImpl = () => Promise.resolve(makeJob(runningStage))
  getUpdateAllStatusImpl = () => Promise.resolve(null) // mount: no existing job

  const wrapper = mount(CodeSyncView, {
    global: { plugins: [i18n], stubs: { ScheduleModal: true, CodeSourceModal: true } },
  })
  await flushPromises() // onMounted

  // Now every subsequent poll fails transiently (control plane restarting).
  getUpdateAllStatusImpl = () => Promise.resolve(undefined)

  // Click the active "Update Everything" CTA.
  const cta = wrapper
    .findAll('button')
    .find((b) => b.text().includes(en.codeSyncView.updateAll))
  expect(cta).toBeTruthy()
  await cta!.trigger('click')
  await flushPromises() // startUpdateAll resolves → schedules first poll at 1000ms

  // First poll (transient error → transientErrors = 1).
  await vi.advanceTimersByTimeAsync(1000)
  await flushPromises()
  return wrapper
}

describe('CodeSyncView reconnecting affordance (#12593)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders the reconnecting notice + amber banner immediately on a stage-3 transient error', async () => {
    const wrapper = await mountAndStartWithTransientError('slm_self_update')
    const text = wrapper.text()
    // Inline "reconnecting… (attempt 1)" notice (interpolated attempt count).
    expect(text).toContain('reconnecting')
    expect(text).toContain('attempt 1')
    // Amber restarting banner surfaces right away (not after 30 errors).
    expect(text).toContain(en.codeSyncView.sLMManagerRestarting)
  })

  it('does NOT show the reconnecting affordance for a non-stage-3 transient error', async () => {
    const wrapper = await mountAndStartWithTransientError('fleet_nodes')
    const text = wrapper.text()
    // No "attempt N" reconnecting copy while a non-stage-3 stage is running.
    expect(text).not.toContain('attempt 1')
    // The stage-3-specific "reconnecting..." stage label must not appear.
    expect(text).not.toContain(en.codeSyncView.pipelineStageReconnecting)
  })
})
