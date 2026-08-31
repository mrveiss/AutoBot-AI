// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #12681: a heartbeat that never dispatched records SKIPPED and stores the
// reason in `error`, which `GET /api/llc/agents/{id}/runs` has always returned.
// The monitor rendered the status and dropped the reason, so "skipped" looked
// identical whether the CLI was missing, a cooldown was active, or the agent
// had no work — an operator had to read the database to tell them apart.
//
// These mount the component rather than asserting on the response shape: the
// field being present in the payload proves nothing while the template never
// reads it, which is exactly how this stayed invisible.

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const get = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get, post: vi.fn() }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth: vi.fn() }))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '' }))

import HeartbeatMonitor from '../HeartbeatMonitor.vue'

const AGENT = { id: 'a1', name: 'Agent One', heartbeat_enabled: true }
const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
const LABELS = en.llc.heartbeat

// The component starts a 15s auto-refresh interval on mount, cleared only by
// onUnmounted. Without this the handle outlives every test in the file.
let mounted: ReturnType<typeof mount> | null = null

/** Mount the monitor and open one agent's run history. */
async function mountWithRuns(runs: Record<string, unknown>[]) {
  get.mockImplementation((url: string) =>
    url.includes('/runs') ? Promise.resolve(runs) : Promise.resolve([AGENT]),
  )
  const wrapper = mount(HeartbeatMonitor, {
    props: { companyId: 'c1' },
    global: { plugins: [i18n] },
  })
  await flushPromises()
  await wrapper.find('.agent-row').trigger('click')
  await flushPromises()
  mounted = wrapper
  return wrapper
}

describe('HeartbeatMonitor surfaces why a run was skipped (#12681)', () => {
  beforeEach(() => {
    get.mockReset()
  })

  afterEach(() => {
    mounted?.unmount()
    mounted = null
  })

  it('renders the persisted reason for a skipped run', async () => {
    const wrapper = await mountWithRuns([
      {
        id: 'r1',
        status: 'skipped',
        started_at: '2026-01-01T00:00:00Z',
        error: 'adapter binary not available',
      },
    ])

    const reason = wrapper.find('.run-reason')
    expect(reason.exists()).toBe(true)
    expect(reason.text()).toContain('adapter binary not available')
    expect(reason.text()).toContain(LABELS.skipReasonLabel)
  })

  it('labels a failed run as an error rather than a skip', async () => {
    const wrapper = await mountWithRuns([
      { id: 'r2', status: 'failed', started_at: '2026-01-01T00:00:00Z', error: 'adapter crashed' },
    ])

    const reason = wrapper.find('.run-reason')
    expect(reason.exists()).toBe(true)
    expect(reason.text()).toContain(LABELS.errorLabel)
    expect(reason.text()).not.toContain(LABELS.skipReasonLabel)
  })

  // The control: without it the first two would still pass if the row were
  // rendered unconditionally, which would put an empty label on every run.
  it('renders no reason row when the run carries none', async () => {
    const wrapper = await mountWithRuns([
      { id: 'r3', status: 'completed', started_at: '2026-01-01T00:00:00Z', error: null },
    ])

    expect(wrapper.find('.run-item').exists()).toBe(true)
    expect(wrapper.find('.run-reason').exists()).toBe(false)
  })
})
