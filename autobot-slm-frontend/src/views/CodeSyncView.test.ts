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
import type {
  FleetSyncJobStatus,
  FleetSyncResponse,
  PendingNode,
  UpdateAllJob,
  UpdateAllStage,
} from '@/composables/useCodeSync'

// Controllable poll responses (swapped per-test).
let getUpdateAllStatusImpl: () => Promise<UpdateAllJob | null | undefined>
let startUpdateAllImpl: () => Promise<UpdateAllJob | null>
// #13157: fleet sync job wiring — swapped per-test like the update-all pair.
let syncFleetImpl: () => Promise<FleetSyncResponse> = () =>
  Promise.resolve({ success: true, message: 'queued', job_id: 'job-fleet', nodes_queued: 1 })
let getJobStatusImpl: () => Promise<FleetSyncJobStatus | null> = () => Promise.resolve(null)
let getRecentJobsImpl: () => Promise<FleetSyncJobStatus[]> = () => Promise.resolve([])
const pendingNodesRef = ref<PendingNode[]>([])

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
      pendingNodes: pendingNodesRef,
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
      syncFleet: () => syncFleetImpl(),
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
      getJobStatus: () => getJobStatusImpl(),
      getRecentJobs: () => getRecentJobsImpl(),
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
    skipped_fleet_nodes: 0,
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

/**
 * #13138 — `UpdateAllJob.status` omitted `'partial'`, the terminal status the
 * backend sets whenever the fleet stage skips a non-operational node
 * (`autobot-slm-backend/api/code_sync.py:4940`, introduced by #11511).
 *
 * The failure banner matches only `'failed'` and the success banner only
 * `'completed' | 'already_current'`, so a partial run finished with NO outcome
 * shown at all. These tests pin the amber partial banner and its skipped count,
 * and prove the success/failure branches still do not claim it.
 */
describe('CodeSyncView update-all terminal outcome (#13138)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  async function mountWithTerminalJob(job: UpdateAllJob) {
    getUpdateAllStatusImpl = () => Promise.resolve(job)
    const wrapper = mount(CodeSyncView, {
      global: { plugins: [i18n], stubs: { ScheduleModal: true, CodeSourceModal: true } },
    })
    await flushPromises() // onMounted -> _checkExistingUpdateAllJob
    return wrapper
  }

  function terminalJob(status: UpdateAllJob['status'], skipped: number): UpdateAllJob {
    return {
      ...makeJob('fleet_nodes'),
      status,
      stages: [makeStage('fleet_nodes', 'success')],
      total_fleet_nodes: 3,
      completed_fleet_nodes: 2,
      skipped_fleet_nodes: skipped,
      completed_at: '2026-01-01T00:05:00Z',
    }
  }

  it('renders the partial banner with the skipped node count', async () => {
    const wrapper = await mountWithTerminalJob(terminalJob('partial', 1))
    const text = wrapper.text()
    expect(text).toContain('1 node(s) skipped')
    // Must not be mistaken for a clean success.
    expect(text).not.toContain(en.codeSyncView.alreadyCurrent)
  })

  it('interpolates a skipped count greater than one', async () => {
    const wrapper = await mountWithTerminalJob(terminalJob('partial', 2))
    expect(wrapper.text()).toContain('2 node(s) skipped')
  })

  it('does not render the partial banner for a fully completed job', async () => {
    const wrapper = await mountWithTerminalJob(terminalJob('completed', 0))
    expect(wrapper.text()).not.toContain('node(s) skipped')
  })

  it('does not render the partial banner for a failed job', async () => {
    const wrapper = await mountWithTerminalJob(terminalJob('failed', 0))
    expect(wrapper.text()).not.toContain('node(s) skipped')
  })
})

/**
 * #13156 — the backend writes a human-readable summary into `stage.message`
 * (`autobot-slm-backend/api/code_sync.py:4473`, `:4742`, `:4938`, `:5025`),
 * including the explanation for a skipped or partially-applied fleet stage.
 * The template never rendered it, so after #13138 an operator could see THAT a
 * run was partial but not WHY.
 *
 * Note the fleet stage of a partial run ends `success`, not `failed`/`skipped`
 * (`code_sync.py:4937-4941`), so these pin the message on a `success` stage
 * too — a "non-terminal statuses only" filter would have missed the very case
 * the issue was filed about.
 */
describe('CodeSyncView stage.message rendering (#13156)', () => {
  async function mountWithJob(job: UpdateAllJob) {
    getUpdateAllStatusImpl = () => Promise.resolve(job)
    const wrapper = mount(CodeSyncView, {
      global: { plugins: [i18n], stubs: { ScheduleModal: true, CodeSourceModal: true } },
    })
    await flushPromises() // onMounted -> _checkExistingUpdateAllJob
    return wrapper
  }

  function stageWithMessage(
    name: string,
    status: UpdateAllStage['status'],
    message: string,
  ): UpdateAllStage {
    return { ...makeStage(name, status), message }
  }

  it('renders the fleet stage message that explains a partial run', async () => {
    const summary = 'Updated 2/3 nodes (1 skipped — not operational)'
    const wrapper = await mountWithJob({
      ...makeJob('fleet_nodes'),
      status: 'partial',
      stages: [stageWithMessage('fleet_nodes', 'success', summary)],
      total_fleet_nodes: 3,
      completed_fleet_nodes: 2,
      skipped_fleet_nodes: 1,
      completed_at: '2026-01-01T00:05:00Z',
    })
    // The reason is on screen, not merely present on the job object.
    expect(wrapper.text()).toContain(summary)
    expect(wrapper.find('[data-testid="stage-message"]').text()).toBe(summary)
    // ...alongside the #13138 partial banner that says only THAT it was partial.
    expect(wrapper.text()).toContain('1 node(s) skipped')
  })

  it('renders the message of a failed stage', async () => {
    const reason = 'git fetch returned no remote commit'
    const wrapper = await mountWithJob({
      ...makeJob('github_fetch'),
      status: 'failed',
      stages: [stageWithMessage('github_fetch', 'failed', reason)],
      failure_reason: reason,
    })
    expect(wrapper.find('[data-testid="stage-message"]').text()).toBe(reason)
  })

  it('renders the message of a skipped stage', async () => {
    const reason = 'SLM node not found in DB — skipping self-update'
    const wrapper = await mountWithJob({
      ...makeJob('slm_self_update'),
      status: 'completed',
      stages: [stageWithMessage('slm_self_update', 'skipped', reason)],
    })
    expect(wrapper.find('[data-testid="stage-message"]').text()).toBe(reason)
  })

  it('renders one message element per stage that carries one', async () => {
    const wrapper = await mountWithJob({
      ...makeJob('fleet_nodes'),
      status: 'running',
      stages: [
        stageWithMessage('github_fetch', 'success', 'Latest commit: abcdef123456'),
        makeStage('code_source_pull', 'pending'), // message: null
        stageWithMessage('fleet_nodes', 'running', 'Syncing fleet node n1 ...'),
      ],
    })
    const messages = wrapper.findAll('[data-testid="stage-message"]')
    expect(messages).toHaveLength(2)
    expect(messages.map((m) => m.text())).toEqual([
      'Latest commit: abcdef123456',
      'Syncing fleet node n1 ...',
    ])
  })

  it('renders no message element when the backend sent none', async () => {
    const wrapper = await mountWithJob({
      ...makeJob('fleet_nodes'),
      stages: [makeStage('fleet_nodes', 'running')],
    })
    expect(wrapper.findAll('[data-testid="stage-message"]')).toHaveLength(0)
  })
})

/**
 * #13157 — `useCodeSync.getJobStatus` / `getRecentJobs` had no production
 * caller, so `FleetSyncJobStatus.failure_reason` (restored to the derived type
 * by #13138) had no route to the screen: "Sync Selected" / "Sync All" queued an
 * asynchronous per-node rollout and then threw the returned `job_id` away.
 *
 * These assert the rendered text an operator actually reads, not that the
 * composable function was called.
 */
describe('CodeSyncView fleet sync job wiring (#13157)', () => {
  const FAILURE_REASON = 'Fleet node n2 playbook failed: FAILED! => apt lock held'

  function fleetJob(overrides: Partial<FleetSyncJobStatus> = {}): FleetSyncJobStatus {
    return {
      job_id: 'job-fleet-1',
      status: 'running',
      strategy: 'rolling',
      total_nodes: 2,
      completed_nodes: 1,
      failed_nodes: 0,
      failure_reason: null,
      nodes: [],
      created_at: '2026-01-01T00:00:00Z',
      completed_at: null,
      ...overrides,
    }
  }

  beforeEach(() => {
    vi.useFakeTimers()
    getUpdateAllStatusImpl = () => Promise.resolve(null)
    getRecentJobsImpl = () => Promise.resolve([])
    getJobStatusImpl = () => Promise.resolve(null)
    syncFleetImpl = () =>
      Promise.resolve({ success: true, message: 'queued', job_id: 'job-fleet-1', nodes_queued: 2 })
    pendingNodesRef.value = [
      {
        node_id: 'n2',
        hostname: 'worker-2',
        ip_address: '10.0.0.2',
        current_version: 'aaaaaaaaaaaa',
        code_status: 'outdated',
      },
    ]
  })
  afterEach(() => {
    vi.useRealTimers()
    pendingNodesRef.value = []
  })

  async function mountAndOpenAdvanced() {
    const wrapper = mount(CodeSyncView, {
      global: { plugins: [i18n], stubs: { ScheduleModal: true, CodeSourceModal: true } },
    })
    await flushPromises() // onMounted
    const toggle = wrapper
      .findAll('button')
      .find((b) => b.text().includes(en.codeSyncView.advancedDiagnostics))
    expect(toggle).toBeTruthy()
    await toggle!.trigger('click')
    await flushPromises() // showAdvanced watcher -> loadRecentFleetJobs
    return wrapper
  }

  it('renders the failure reason of the job started from this page', async () => {
    getJobStatusImpl = () =>
      Promise.resolve(
        fleetJob({
          status: 'failed',
          completed_nodes: 1,
          failed_nodes: 1,
          failure_reason: FAILURE_REASON,
          completed_at: '2026-01-01T00:02:00Z',
          nodes: [
            { node_id: 'n1', hostname: 'worker-1', status: 'success', message: null },
            { node_id: 'n2', hostname: 'worker-2', status: 'failed', message: 'apt lock held' },
          ],
        }),
      )

    const wrapper = await mountAndOpenAdvanced()
    const syncAll = wrapper
      .findAll('button')
      .find((b) => b.text().trim() === en.codeSyncView.syncAll)
    expect(syncAll).toBeTruthy()
    await syncAll!.trigger('click')
    await flushPromises() // syncFleet resolves -> first poll scheduled at 2000ms
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()

    // The reason the backend recorded is on screen.
    expect(wrapper.find('[data-testid="fleet-job-failure-reason"]').text()).toContain(
      FAILURE_REASON,
    )
    // ...as is the per-node explanation and the failed-node count.
    const jobPanel = wrapper.find('[data-testid="fleet-sync-job"]')
    expect(jobPanel.text()).toContain('worker-2')
    expect(jobPanel.text()).toContain('apt lock held')
    expect(jobPanel.text()).toContain('1 failed')
    expect(jobPanel.text()).toContain('1 / 2 nodes')
  })

  it('keeps polling a running job and stops once it reaches a terminal status', async () => {
    let call = 0
    getJobStatusImpl = () => {
      call += 1
      return Promise.resolve(
        call === 1
          ? fleetJob({ status: 'running', completed_nodes: 1 })
          : fleetJob({ status: 'completed', completed_nodes: 2 }),
      )
    }

    const wrapper = await mountAndOpenAdvanced()
    const syncAll = wrapper
      .findAll('button')
      .find((b) => b.text().trim() === en.codeSyncView.syncAll)
    await syncAll!.trigger('click')
    await flushPromises()

    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(wrapper.find('[data-testid="fleet-sync-job"]').text()).toContain('1 / 2 nodes')

    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(wrapper.find('[data-testid="fleet-sync-job"]').text()).toContain('2 / 2 nodes')

    // Terminal status stops the loop — no further getJobStatus calls.
    const callsAtTerminal = call
    await vi.advanceTimersByTimeAsync(10000)
    await flushPromises()
    expect(call).toBe(callsAtTerminal)
  })

  it('lists recent jobs with their failure reason when Advanced is opened', async () => {
    getRecentJobsImpl = () =>
      Promise.resolve([
        fleetJob({
          job_id: 'job-older',
          status: 'failed',
          failed_nodes: 2,
          failure_reason: FAILURE_REASON,
          completed_at: '2026-01-01T00:02:00Z',
        }),
      ])

    const wrapper = await mountAndOpenAdvanced()
    const rows = wrapper.findAll('[data-testid="recent-fleet-job"]')
    expect(rows).toHaveLength(1)
    expect(rows[0].text()).toContain('job-older')
    expect(rows[0].text()).toContain(FAILURE_REASON)
    expect(wrapper.text()).not.toContain(en.codeSyncView.noRecentFleetJobs)
  })

  it('shows the empty state when no fleet sync job has ever run', async () => {
    const wrapper = await mountAndOpenAdvanced()
    expect(wrapper.findAll('[data-testid="recent-fleet-job"]')).toHaveLength(0)
    expect(wrapper.text()).toContain(en.codeSyncView.noRecentFleetJobs)
  })
})
