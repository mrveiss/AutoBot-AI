// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #22145 (owner 2026-11-24): the chat Desktop picker lists the desktop VM from the BACKEND's resolved
 * endpoint (the SLM registry) -- the same answer the controls use -- next to the user's /secrets hosts.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const call = vi.fn()
const warn = vi.fn()
vi.mock('@/utils/debugUtils', () => ({ createLogger: () => ({ warn: (...a: unknown[]) => warn(...a), info: vi.fn(), error: vi.fn(), debug: vi.fn() }) }))
vi.mock('@/utils/ApiClient', () => ({ default: { call: (...a: unknown[]) => call(...a) } }))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))
const infra = ref([{ id: 's1', name: 'Mine', host: 'mine.example.test', username: 'u', capabilities: ['ssh', 'vnc'] }])
vi.mock('@/composables/useHostSelection', () => ({
  useHostSelection: () => ({ hosts: infra, loading: ref(false), error: ref(null), loadHosts: vi.fn(async () => {}) })
}))

import { useHostSelector } from '../useHostSelector'
import { DESKTOP_VM_HOST_ID } from '@/config/vnc-client'

describe('chat Desktop picker', () => {
  beforeEach(() => { call.mockReset(); warn.mockReset() })

  it('lists the desktop VM first, from the backend endpoint, plus the /secrets hosts', async () => {
    call.mockResolvedValue({ host: 'desk.example.test', port: 6090, source: 'registry' })
    const sel = useHostSelector({ requiredCapability: 'vnc', includeDesktopVm: true })
    await sel.loadHosts()
    expect(call).toHaveBeenCalledWith('get', '/api/vnc-proxy/desktop/endpoint')
    expect(sel.hosts.value.map((h) => h.id)).toEqual([DESKTOP_VM_HOST_ID, 's1'])
    expect(sel.hosts.value[0]).toMatchObject({ host: 'desk.example.test', vnc_port: 6090 })
  })

  it('has no desktop VM entry when the backend returns no endpoint (none registered, no fallback)', async () => {
    call.mockResolvedValue(null)
    const sel = useHostSelector({ requiredCapability: 'vnc', includeDesktopVm: true })
    await sel.loadHosts()
    expect(sel.hosts.value.map((h) => h.id)).toEqual(['s1'])
  })

  it('never asks for it unless the picker opts in', async () => {
    const sel = useHostSelector({ requiredCapability: 'vnc' })
    await sel.loadHosts()
    expect(call).not.toHaveBeenCalled()
    expect(sel.hosts.value.map((h) => h.id)).toEqual(['s1'])
  })

  it('has no entry and logs when the endpoint call fails', async () => {
    call.mockImplementation(async () => {
      throw new Error('503')
    })
    const sel = useHostSelector({ requiredCapability: 'vnc', includeDesktopVm: true })
    await sel.loadHosts()
    expect(sel.hosts.value.map((h) => h.id)).toEqual(['s1'])
    expect(warn).toHaveBeenCalled()
  })
})
