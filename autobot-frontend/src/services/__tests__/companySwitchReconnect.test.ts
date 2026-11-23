// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/** The two singleton `/ws/live` services reopen under a newly selected company (#21997). */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { useUserStore } from '@/stores/useUserStore'
import { useLlcCompanyStore } from '@/stores/useLlcCompanyStore'
import { MockWebSocket } from '../../test/mocks/websocket-mock'

const COMPANY = '11111111-1111-4111-8111-111111111111'
const TOKEN = ['fixture', 'not-a-real', 'value'].join('.')

describe.each([
  ['LiveEventService', '@/services/LiveEventService', '_autobotLiveEventInitialized'],
  ['GlobalWebSocketService', '@/services/GlobalWebSocketService', '_autobotWebSocketInitialized'],
])('%s company switch (#21997)', (_name, path, flag) => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.resetModules()
    delete (window as unknown as Record<string, unknown>)[flag]
    setActivePinia(createPinia())
    useUserStore().authState.token = TOKEN
    MockWebSocket.mockImplementation()
    MockWebSocket.clearInstances()
  })

  afterEach(() => {
    MockWebSocket.restoreImplementation()
    MockWebSocket.clearInstances()
    vi.useRealTimers()
  })

  it('reconnects with the new company_id in the URL', async () => {
    await import(/* @vite-ignore */ path)
    await vi.advanceTimersByTimeAsync(1500)
    const before = MockWebSocket.getAllInstances().length
    expect(before).toBeGreaterThan(0)
    expect(MockWebSocket.getLatestInstance()!.url).not.toContain('company_id')

    await vi.dynamicImportSettled()
    useLlcCompanyStore().selectedCompanyId = COMPANY
    await nextTick()
    await vi.advanceTimersByTimeAsync(2500)

    expect(MockWebSocket.getAllInstances().length).toBeGreaterThan(before)
    expect(MockWebSocket.getLatestInstance()!.url).toContain(`company_id=${COMPANY}`)
  })
})
