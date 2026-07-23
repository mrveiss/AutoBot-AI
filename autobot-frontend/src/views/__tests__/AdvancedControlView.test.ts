// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Tests for AdvancedControlView.vue (#12162, #12102, #11506 T1 — Stage 1).
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
const mockLoading = ref(false)
const mockError = ref<string | null>(null)

const mockLoadTakeovers = vi.fn().mockResolvedValue(undefined)
const mockApprove = vi.fn().mockResolvedValue(true)
const mockPause = vi.fn().mockResolvedValue(true)
const mockResume = vi.fn().mockResolvedValue(true)
const mockComplete = vi.fn().mockResolvedValue(true)

vi.mock('@/composables/useAdvancedControl', () => ({
  useAdvancedControl: () => ({
    pendingTakeovers: mockPendingTakeovers,
    activeTakeovers: mockActiveTakeovers,
    takeoverStatus: mockTakeoverStatus,
    loading: mockLoading,
    error: mockError,
    loadTakeovers: mockLoadTakeovers,
    approve: mockApprove,
    pause: mockPause,
    resume: mockResume,
    complete: mockComplete,
    action: vi.fn(),
  }),
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
    mockLoading.value = false
    mockError.value = null
    mockLoadTakeovers.mockClear()
    mockApprove.mockClear()
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
})
