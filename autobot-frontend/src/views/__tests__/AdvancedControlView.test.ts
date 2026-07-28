// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Tests for AdvancedControlView.vue (#12162, #12102, #11506 T1 — Stage 1;
// #12169, #12102 — Stage 2 streaming sessions tab; #12173, #12102 —
// Stage 3 system monitoring + emergency-stop tab).
// Mocks useAdvancedControl so no real HTTP calls are made, and asserts the
// /admin/advanced-control route carries the same admin guard meta as its
// sibling admin routes (router/index.ts requiresAdmin check).

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { ref } from 'vue'
import en from '@/i18n/locales/en.json'
import { routes } from '@/router'

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

// Real Vue refs so template auto-unwrapping works the same as the live composable.
const mockPendingTakeovers = ref<unknown[]>([])
const mockActiveTakeovers = ref<unknown[]>([])
const mockTakeoverStatus = ref<unknown>(null)
const mockStreamingSessions = ref<unknown[]>([])
const mockStreamingCapabilities = ref<unknown>(null)
const mockSystemStatus = ref<unknown>(null)
const mockSystemHealth = ref<unknown>(null)
const mockLoading = ref(false)
const mockError = ref<string | null>(null)

const mockLoadTakeovers = vi.fn().mockResolvedValue(undefined)
const mockApprove = vi.fn().mockResolvedValue(true)
const mockPause = vi.fn().mockResolvedValue(true)
const mockResume = vi.fn().mockResolvedValue(true)
const mockComplete = vi.fn().mockResolvedValue(true)
const mockLoadStreaming = vi.fn().mockResolvedValue(undefined)
const mockCreateStreaming = vi.fn().mockResolvedValue(true)
const mockTerminateStreaming = vi.fn().mockResolvedValue(true)
const mockLoadMonitoring = vi.fn().mockResolvedValue(undefined)
const mockEmergencyStop = vi.fn().mockResolvedValue(true)

vi.mock('@/composables/useAdvancedControl', () => ({
  useAdvancedControl: () => ({
    pendingTakeovers: mockPendingTakeovers,
    activeTakeovers: mockActiveTakeovers,
    takeoverStatus: mockTakeoverStatus,
    streamingSessions: mockStreamingSessions,
    streamingCapabilities: mockStreamingCapabilities,
    systemStatus: mockSystemStatus,
    systemHealth: mockSystemHealth,
    loading: mockLoading,
    error: mockError,
    loadTakeovers: mockLoadTakeovers,
    approve: mockApprove,
    pause: mockPause,
    resume: mockResume,
    complete: mockComplete,
    action: vi.fn(),
    loadStreaming: mockLoadStreaming,
    createStreaming: mockCreateStreaming,
    terminateStreaming: mockTerminateStreaming,
    loadMonitoring: mockLoadMonitoring,
    emergencyStop: mockEmergencyStop,
    getMonitoringWebSocketUrl: vi.fn().mockReturnValue('ws://host/ws/monitoring'),
  }),
}))

const mockConfirm = vi.fn().mockResolvedValue(true)
vi.mock('@/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: mockConfirm }),
}))

const mockNotifySuccess = vi.fn()
vi.mock('@/composables/useNotificationBus', () => ({
  useNotificationBus: () => ({ notifySuccess: mockNotifySuccess }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ debug: vi.fn(), error: vi.fn(), warn: vi.fn(), info: vi.fn() }),
}))

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

import AdvancedControlView from '../AdvancedControlView.vue'

function mountView() {
  return mount(AdvancedControlView, {
    global: { plugins: [i18n] },
  })
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('AdvancedControlView.vue', () => {
  beforeEach(() => {
    mockPendingTakeovers.value = []
    mockActiveTakeovers.value = []
    mockTakeoverStatus.value = null
    mockStreamingSessions.value = []
    mockStreamingCapabilities.value = null
    mockSystemStatus.value = null
    mockSystemHealth.value = null
    mockLoading.value = false
    mockError.value = null
    mockLoadTakeovers.mockClear()
    mockApprove.mockClear()
    mockLoadStreaming.mockClear()
    mockCreateStreaming.mockClear()
    mockTerminateStreaming.mockClear()
    mockLoadMonitoring.mockClear()
    mockEmergencyStop.mockClear().mockResolvedValue(true)
    mockConfirm.mockClear().mockResolvedValue(true)
    mockNotifySuccess.mockClear()
  })

  it('is registered as an admin-gated route (same guard as sibling admin routes)', () => {
    const route = routes.find((r) => r.path === '/admin/advanced-control')
    expect(route).toBeTruthy()
    expect(route?.meta?.requiresAuth).toBe(true)
    expect(route?.meta?.admin).toBe(true)
  })

  it('renders the tab shell and the empty pending/active queue', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('Advanced Control')
    expect(wrapper.text()).toContain('Takeover Queue')
    expect(wrapper.text()).toContain('No pending requests')
    expect(wrapper.text()).toContain('No active sessions')
    expect(mockLoadTakeovers).toHaveBeenCalled()
  })

  it('renders a pending request row with an approve action', async () => {
    mockPendingTakeovers.value = [
      {
        request_id: 'r1',
        trigger: 'MANUAL_REQUEST',
        reason: 'needs a human',
        requesting_agent: 'agent-1',
        affected_tasks: [],
        priority: 'HIGH',
        created_at: '2026-07-23T00:00:00Z',
        timeout_at: null,
        auto_approve: false,
      },
    ]

    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('needs a human')
    expect(wrapper.text()).toContain('agent-1')

    const approveBtn = wrapper.find('button.btn-success')
    expect(approveBtn.exists()).toBe(true)
    await approveBtn.trigger('click')
    expect(mockApprove).toHaveBeenCalledWith('r1')
  })

  it('surfaces the composable error via the error banner', async () => {
    mockError.value = 'Failed to load takeovers'

    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('Failed to load takeovers')
  })

  // -------------------------------------------------------------------------
  // Streaming Sessions tab (#12169, #12102 — Stage 2)
  // -------------------------------------------------------------------------

  async function selectStreamingTab(wrapper: ReturnType<typeof mountView>) {
    const tabs = wrapper.findAll('button[role="tab"]')
    const streamingTab = tabs.find((btn) => btn.text().includes('Streaming'))
    expect(streamingTab).toBeTruthy()
    await streamingTab!.trigger('click')
    await flushPromises()
  }

  it('enables the Streaming tab, loads sessions on activation, and renders the empty state', async () => {
    const wrapper = mountView()
    await flushPromises()

    await selectStreamingTab(wrapper)

    expect(mockLoadStreaming).toHaveBeenCalled()
    expect(wrapper.text()).toContain('No active streaming sessions')
  })

  it('renders a streaming session row with a terminate action', async () => {
    mockStreamingSessions.value = [
      {
        session_id: 's1',
        user_id: 'u1',
        vnc_port: 5901,
        novnc_port: 6901,
        display: ':1',
        created_at: '2026-07-23T00:00:00Z',
        status: 'active',
      },
    ]
    mockStreamingCapabilities.value = {
      vnc_available: true,
      novnc_available: true,
      max_sessions: 4,
      supported_resolutions: ['1920x1080'],
      supported_depths: [24],
    }

    const wrapper = mountView()
    await flushPromises()
    await selectStreamingTab(wrapper)

    expect(wrapper.text()).toContain('s1')
    expect(wrapper.text()).toContain('u1')

    const terminateBtn = wrapper.find('button.btn-danger')
    expect(terminateBtn.exists()).toBe(true)
    await terminateBtn.trigger('click')
    expect(mockTerminateStreaming).toHaveBeenCalledWith('s1')
  })

  it('submits the new-session form with the StreamingSessionRequest shape', async () => {
    const wrapper = mountView()
    await flushPromises()
    await selectStreamingTab(wrapper)

    const newSessionBtn = wrapper
      .findAll('button')
      .find((btn) => btn.text().includes('New Session'))
    expect(newSessionBtn).toBeTruthy()
    await newSessionBtn!.trigger('click')

    await wrapper.find('#streaming-user-id').setValue('user-123')
    await wrapper.find('#streaming-resolution').setValue('1920x1080')
    await wrapper.find('#streaming-depth').setValue(24)

    await wrapper.find('form.streaming-create-form').trigger('submit.prevent')
    await flushPromises()

    expect(mockCreateStreaming).toHaveBeenCalledWith({
      user_id: 'user-123',
      resolution: '1920x1080',
      depth: 24,
    })
  })

  // -------------------------------------------------------------------------
  // Monitoring tab (#12173, #12102 — Stage 3)
  // -------------------------------------------------------------------------

  async function selectMonitoringTab(wrapper: ReturnType<typeof mountView>) {
    const tabs = wrapper.findAll('button[role="tab"]')
    const monitoringTab = tabs.find((btn) => btn.text().includes('Monitoring'))
    expect(monitoringTab).toBeTruthy()
    await monitoringTab!.trigger('click')
    await flushPromises()
  }

  const systemHealthFixture = {
    status: 'healthy',
    desktop_streaming_available: true,
    novnc_available: true,
    active_streaming_sessions: 2,
    pending_takeovers: 1,
    active_takeovers: 0,
    paused_tasks: 3,
  }

  const systemStatusFixture = {
    system_status: {
      status: 'healthy',
      timestamp: 1700000000,
      uptime_seconds: 3661,
      streaming_capabilities: {
        vnc_available: true,
        novnc_available: true,
        max_sessions: 4,
        supported_resolutions: ['1920x1080'],
        supported_depths: [24],
      },
    },
    active_sessions: [],
    pending_takeovers: [],
    active_takeovers: [],
    resource_usage: {
      cpu_percent: 12.5,
      memory_percent: 40.1,
      disk_usage: 55.0,
      process_count: 210,
      load_average: [0.1, 0.2, 0.3],
    },
  }

  it('enables the Monitoring tab and loads monitoring data on activation', async () => {
    const wrapper = mountView()
    await flushPromises()

    await selectMonitoringTab(wrapper)

    expect(mockLoadMonitoring).toHaveBeenCalled()
  })

  it('renders health and resource-usage summaries once monitoring data loads', async () => {
    mockSystemHealth.value = systemHealthFixture
    mockSystemStatus.value = systemStatusFixture

    const wrapper = mountView()
    await flushPromises()
    await selectMonitoringTab(wrapper)

    expect(wrapper.text()).toContain('Healthy')
    expect(wrapper.text()).toContain('12.5%')
    expect(wrapper.text()).toContain('210')
  })

  it('renders the empty state when no monitoring data is available', async () => {
    const wrapper = mountView()
    await flushPromises()
    await selectMonitoringTab(wrapper)

    expect(wrapper.text()).toContain('No monitoring data')
  })

  it('requires confirmation before calling emergencyStop, and does nothing if cancelled', async () => {
    mockConfirm.mockResolvedValueOnce(false)
    mockSystemHealth.value = systemHealthFixture
    mockSystemStatus.value = systemStatusFixture

    const wrapper = mountView()
    await flushPromises()
    await selectMonitoringTab(wrapper)

    const stopBtn = wrapper.find('button.btn-danger-full')
    expect(stopBtn.exists()).toBe(true)
    await stopBtn.trigger('click')
    await flushPromises()

    expect(mockConfirm).toHaveBeenCalled()
    expect(mockEmergencyStop).not.toHaveBeenCalled()
    expect(mockNotifySuccess).not.toHaveBeenCalled()
  })

  it('calls emergencyStop and shows a success toast once confirmed', async () => {
    mockConfirm.mockResolvedValueOnce(true)
    mockSystemHealth.value = systemHealthFixture
    mockSystemStatus.value = systemStatusFixture

    const wrapper = mountView()
    await flushPromises()
    await selectMonitoringTab(wrapper)

    const stopBtn = wrapper.find('button.btn-danger-full')
    await stopBtn.trigger('click')
    await flushPromises()

    expect(mockConfirm).toHaveBeenCalled()
    expect(mockEmergencyStop).toHaveBeenCalled()
    expect(mockNotifySuccess).toHaveBeenCalled()
  })
})
