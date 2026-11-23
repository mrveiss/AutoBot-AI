// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/** A company switch reopens a live socket with the new `company_id` in its URL (#21997). */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { effectScope, nextTick, type EffectScope } from 'vue'
import { useWebSocket } from '../useWebSocket'
import { useLlcCompanyStore } from '@/stores/useLlcCompanyStore'
import { MockWebSocket } from '../../test/mocks/websocket-mock'

const COMPANY = '11111111-1111-4111-8111-111111111111'
let scope: EffectScope

describe('useWebSocket company switch (#21997)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    setActivePinia(createPinia())
    MockWebSocket.mockImplementation()
    MockWebSocket.clearInstances()
  })

  afterEach(() => {
    scope?.stop()
    MockWebSocket.restoreImplementation()
    MockWebSocket.clearInstances()
    vi.useRealTimers()
  })

  it('reconnects under the newly selected company', async () => {
    scope = effectScope()
    const socket = scope.run(() => useWebSocket('wss://backend.example/api/ws/chat-1', { companyScoped: true }))!
    await vi.advanceTimersByTimeAsync(20)
    expect(socket.isConnected.value).toBe(true)
    expect(MockWebSocket.getLatestInstance()!.url).not.toContain('company_id')

    useLlcCompanyStore().selectedCompanyId = COMPANY
    await nextTick()
    await vi.advanceTimersByTimeAsync(500)

    expect(MockWebSocket.getAllInstances()).toHaveLength(2)
    expect(MockWebSocket.getLatestInstance()!.url).toContain(`company_id=${COMPANY}`)
  })

  it('leaves a socket that is not company-scoped alone (a terminal never gets company_id)', async () => {
    useLlcCompanyStore().selectedCompanyId = COMPANY
    scope = effectScope()
    scope.run(() => useWebSocket('wss://backend.example/api/terminal/ws/ssh/h1'))
    await vi.advanceTimersByTimeAsync(20)
    expect(MockWebSocket.getLatestInstance()!.url).not.toContain('company_id')

    useLlcCompanyStore().selectedCompanyId = ''
    await nextTick()
    await vi.advanceTimersByTimeAsync(500)
    expect(MockWebSocket.getAllInstances()).toHaveLength(1)
  })
})
