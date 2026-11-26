// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #22144: a blocked desktop VM stays blocked, and
 * Reconnect repeats the URL initialisation so a registry that recovered lets the viewer load.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'

const blockedKey = vi.fn<() => Promise<string | null>>()
vi.mock('@/composables/useDesktopVm', () => ({ desktopVmBlockedKey: () => blockedKey() }))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))
vi.mock('@/composables/useDesktopControlLock', () => ({
  useDesktopControlLock: () => ({
    owner: ref(null), humanActive: ref(false), isMine: ref(false), loading: ref(false),
    refreshStatus: vi.fn(), takeControl: vi.fn(), releaseControl: vi.fn(),
  }),
}))
vi.mock('@/composables/usePollingJob', () => ({ usePollingJob: (fn: () => Promise<void>) => ({ start: () => void fn() }) }))
vi.mock('@/stores/useChatStore', () => ({ useChatStore: () => ({ currentSessionId: null }) }))
vi.mock('@/utils/ApiClient', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
vi.mock('@/components/desktop/DesktopContextPanel.vue', () => ({ default: { template: '<div />' } }))

import DesktopInterface from '../DesktopInterface.vue'
import { DESKTOP_VM_HOST_ID } from '@/config/vnc-client'

const host = { id: DESKTOP_VM_HOST_ID, name: 'Desktop', host: 'desk.example.test', vnc_port: 6090, capabilities: ['vnc'] }
const mountIt = () =>
  mount(DesktopInterface, { props: { host } as never, global: { mocks: { $t: (k: string) => k } } })

describe('DesktopInterface blocked desktop VM', () => {
  beforeEach(() => {
    blockedKey.mockReset()
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, type: 'opaque' })))
  })
  afterEach(() => vi.unstubAllGlobals())

  it('a reachable probe does not turn a blocked desktop VM into Connected', async () => {
    vi.useFakeTimers()
    blockedKey.mockResolvedValue('desktop.interface.desktopVmUnavailable')
    const wrapper = mountIt()
    try {
      await flushPromises()
      await wrapper.vm.$.setupState.checkConnection() // the probe really runs and reaches the server
      expect(fetch).toHaveBeenCalled()
      expect(wrapper.vm.$.setupState.vncUrl).toBe('')
      expect(wrapper.vm.$.setupState.connectionStatus).not.toBe('Connected')
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
    }
  })

  it('a blocked result from a superseded load never overwrites the newer one', async () => {
    let releaseFirst!: (v: string | null) => void
    blockedKey.mockImplementationOnce(() => new Promise(res => { releaseFirst = res })).mockResolvedValue(null)
    const wrapper = mountIt()
    await flushPromises()
    await wrapper.vm.$.setupState.reconnect() // newer load: not blocked, viewer URL set
    await flushPromises()
    expect(wrapper.vm.$.setupState.vncUrl).toContain('desk.example.test')
    releaseFirst('desktop.interface.desktopVmUnavailable') // the older load answers late
    await flushPromises()
    expect(wrapper.vm.$.setupState.vncUrl).toContain('desk.example.test')
    wrapper.unmount()
  })

  it('Reconnect repeats the initialisation and loads the viewer once the registry recovers', async () => {
    blockedKey.mockResolvedValueOnce('desktop.interface.registryUnavailable').mockResolvedValue(null)
    const wrapper = mountIt()
    await flushPromises()
    expect(wrapper.vm.$.setupState.vncUrl).toBe('')
    await wrapper.vm.$.setupState.reconnect()
    await flushPromises()
    expect(blockedKey).toHaveBeenCalledTimes(2)
    expect(wrapper.vm.$.setupState.vncUrl).toContain('desk.example.test')
  })
})
