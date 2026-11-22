// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * KnowledgeResearchPanel reacts to the close of its live research socket only (#21548).
 *
 * useWebSocket is replaced by a double that keeps the options the panel passed, so the spec calls
 * the panel's own `onClose` with `{ current: false }` (a socket that was replaced) and
 * `{ current: true }`. The panel is put in the researching state the way a user does: type a query,
 * press the research button (startResearch awaits checkBrowserStatus, which the mocked ApiClient answers).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'

const stubT = (key: string, _params?: object) => key

vi.mock('vue-i18n', () => ({
  useI18n: vi.fn(),
}))

vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  }),
}))

vi.mock('@/config/ssot-config', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/config/ssot-config')>()),
  getBackendWsUrl: () => 'wss://backend.example',
}))

vi.mock('@/composables/useWebSocket', () => ({
  useWebSocket: vi.fn(),
}))

vi.mock('@/composables/usePollingJob', () => ({
  usePollingJob: vi.fn(),
}))

import { useI18n } from 'vue-i18n'
import ApiClient from '@/utils/ApiClient'
import { useWebSocket, type UseWebSocketOptions } from '@/composables/useWebSocket'
import { usePollingJob } from '@/composables/usePollingJob'
import KnowledgeResearchPanel from '../KnowledgeResearchPanel.vue'

const QUERY = 'vector databases'

let socketOptions: UseWebSocketOptions
let stopPolling: ReturnType<typeof vi.fn>
let wrapper: VueWrapper | null

/** Flush pending promise work (the awaited browser-status call) before asserting. */
const flushAsync = () => new Promise((resolve) => setTimeout(resolve, 0))

const closeEvent = () => new CloseEvent('close', { code: 1006 })

async function startResearch(): Promise<VueWrapper> {
  const view = mount(KnowledgeResearchPanel, {
    global: {
      plugins: [createPinia()],
      mocks: { $t: stubT },
      stubs: { InteractiveScreenshot: true },
    },
  })
  await flushAsync()
  await view.find('input.query-input').setValue(QUERY)
  await view.find('button.btn-primary').trigger('click')
  await flushAsync()
  await nextTick()
  return view
}

describe('KnowledgeResearchPanel when its research socket closes (#21548)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    wrapper = null
    stopPolling = vi.fn()
    vi.mocked(useI18n).mockReturnValue({ t: stubT } as unknown as ReturnType<typeof useI18n>)
    vi.mocked(ApiClient.get).mockResolvedValue({})
    vi.mocked(ApiClient.post).mockResolvedValue({})
    vi.mocked(usePollingJob).mockReturnValue({
      start: vi.fn(),
      stop: stopPolling,
    } as unknown as ReturnType<typeof usePollingJob>)
    vi.mocked(useWebSocket).mockImplementation(((_url: unknown, options: UseWebSocketOptions) => {
      socketOptions = options
      return { send: vi.fn(), connect: vi.fn(), disconnect: vi.fn() }
    }) as unknown as typeof useWebSocket)
  })

  it('keeps researching when a replaced socket closes', async () => {
    wrapper = await startResearch()
    expect(wrapper.find('button.btn-stop').exists()).toBe(true)
    expect(wrapper.find('.status-text').text()).toBe('knowledge.research.statusConnecting')

    socketOptions.onClose!(closeEvent(), { current: false })
    await nextTick()

    expect(wrapper.find('button.btn-stop').exists()).toBe(true)
    expect(wrapper.find('.status-text').text()).toBe('knowledge.research.statusConnecting')
    expect(stopPolling).not.toHaveBeenCalled()
  })

  it('stops researching when the current socket closes', async () => {
    wrapper = await startResearch()
    expect(wrapper.find('button.btn-stop').exists()).toBe(true)

    socketOptions.onClose!(closeEvent(), { current: true })
    await nextTick()

    expect(wrapper.find('button.btn-stop').exists()).toBe(false)
    expect(wrapper.find('.status-text').text()).toBe('knowledge.research.statusDisconnected')
    expect(stopPolling).toHaveBeenCalledTimes(1)
  })
})
