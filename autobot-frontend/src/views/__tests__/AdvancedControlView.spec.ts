// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Tests for AdvancedControlView.vue (#12102).
// Mocks AdvancedControlApiClient so no real HTTP calls are made — verifies the
// view renders, calls the client on mount, and surfaces loading/error states.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

const client = vi.hoisted(() => ({
  getStreamingCapabilities: vi.fn(),
  listStreamingSessions: vi.fn(),
  getTakeoverStatus: vi.fn(),
  getPendingTakeovers: vi.fn(),
  getActiveTakeovers: vi.fn(),
  createStreamingSession: vi.fn(),
  terminateStreamingSession: vi.fn(),
  requestTakeover: vi.fn(),
  approveTakeover: vi.fn(),
  pauseTakeoverSession: vi.fn(),
  resumeTakeoverSession: vi.fn(),
  completeTakeoverSession: vi.fn(),
}))

vi.mock('@/utils/AdvancedControlApiClient', () => ({ default: client }))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ debug: vi.fn(), error: vi.fn(), warn: vi.fn(), info: vi.fn() }),
}))

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

import AdvancedControlView from '../AdvancedControlView.vue'

function ok<T>(data: T) {
  return { success: true, data }
}

function mountView() {
  return mount(AdvancedControlView, {
    global: { plugins: [i18n], stubs: { Icon: true } },
  })
}

function seedHappyPath() {
  client.getStreamingCapabilities.mockResolvedValue(
    ok({ vnc_available: true, novnc_available: true, max_sessions: 5, supported_resolutions: ['1920x1080'], supported_depths: [24] }),
  )
  client.listStreamingSessions.mockResolvedValue(
    ok({ count: 1, sessions: [{ session_id: 'sess-1', user_id: 'alice', vnc_port: 5901, novnc_port: 6081, display: ':1', created_at: '2026-07-22T10:00:00Z', status: 'active' }] }),
  )
  client.getTakeoverStatus.mockResolvedValue(
    ok({ pending_requests_count: 1, active_sessions_count: 0, paused_tasks_count: 0, total_completed_sessions: 3, system_status: 'normal' }),
  )
  client.getPendingTakeovers.mockResolvedValue(
    ok({ count: 1, pending_requests: [{ request_id: 'req-1', trigger: 'MANUAL_REQUEST', reason: 'need help', requesting_agent: 'agent-x', affected_tasks: [], priority: 'HIGH', created_at: '2026-07-22T10:00:00Z', timeout_at: null, auto_approve: false }] }),
  )
  client.getActiveTakeovers.mockResolvedValue(ok({ count: 0, active_sessions: [] }))
}

describe('AdvancedControlView.vue (#12102)', () => {
  beforeEach(() => {
    for (const fn of Object.values(client)) fn.mockReset()
    seedHappyPath()
  })

  it('renders and calls the client streaming + takeover methods on mount', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(client.getStreamingCapabilities).toHaveBeenCalledTimes(1)
    expect(client.listStreamingSessions).toHaveBeenCalledTimes(1)
    expect(client.getTakeoverStatus).toHaveBeenCalledTimes(1)
    expect(client.getPendingTakeovers).toHaveBeenCalledTimes(1)
    expect(client.getActiveTakeovers).toHaveBeenCalledTimes(1)

    // Streaming session + pending takeover rows are rendered
    expect(wrapper.text()).toContain('sess-1')
    expect(wrapper.text()).toContain('alice')
    expect(wrapper.text()).toContain('req-1')
  })

  it('surfaces an error banner when a client call fails', async () => {
    client.getStreamingCapabilities.mockResolvedValue({ success: false, error: 'boom' })

    const wrapper = mountView()
    await flushPromises()

    const banner = wrapper.find('.ac-error-banner')
    expect(banner.exists()).toBe(true)
    expect(banner.text()).toContain('boom')
  })

  it('terminates a streaming session via the client', async () => {
    client.terminateStreamingSession.mockResolvedValue(ok({ success: true, session_id: 'sess-1' }))

    const wrapper = mountView()
    await flushPromises()

    const termBtn = wrapper.findAll('button').find((b) => b.text().includes('Terminate'))
    expect(termBtn).toBeTruthy()
    await termBtn!.trigger('click')
    await flushPromises()

    expect(client.terminateStreamingSession).toHaveBeenCalledWith('sess-1')
    // Session list is refreshed after the action
    expect(client.listStreamingSessions).toHaveBeenCalledTimes(2)
  })

  it('approves a pending takeover with the entered operator', async () => {
    client.approveTakeover.mockResolvedValue(ok({ success: true, session_id: 'ts-1' }))

    const wrapper = mountView()
    await flushPromises()

    const operatorInput = wrapper.find('.ac-approve-cell input')
    await operatorInput.setValue('operator-bob')

    const approveBtn = wrapper.findAll('button').find((b) => b.text().trim() === 'Approve')
    await approveBtn!.trigger('click')
    await flushPromises()

    expect(client.approveTakeover).toHaveBeenCalledWith('req-1', { human_operator: 'operator-bob' })
  })
})
