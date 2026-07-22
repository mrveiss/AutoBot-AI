// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Tests for KnowledgeResearchPanel.vue — visual-browser proxy session isolation (#11925).
 *
 * Discovery: the panel called /playwright/worker-status, /worker-screenshot and
 * /interact with no session/user identifier, so every admin viewing the panel
 * shared the browser-worker's single "default" context (one cookie jar).
 *
 * Covers:
 *  - Two different authenticated users get DIFFERENT derived session ids
 *    (and therefore different worker-status/worker-screenshot/interact buckets).
 *  - The same user's requests stay on a STABLE session id across calls.
 *  - No authenticated user falls back to the shared default bucket (omits
 *    session_id) rather than crashing — preserves the legacy single-session
 *    proxy behavior when identity is unavailable.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'

const stubT = (key: string, _params?: object) => key

// The component calls useI18n() in <script setup> AND uses $t(...) in the
// template — cover both: useI18n() mock here, $t global in every mount().
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

import { useI18n } from 'vue-i18n'
import ApiClient from '@/utils/ApiClient'
import { useUserStore, type UserProfile } from '@/stores/useUserStore'
import KnowledgeResearchPanel from '../KnowledgeResearchPanel.vue'

function makeUser(id: string): UserProfile {
  return {
    id,
    username: `user-${id}`,
    displayName: `User ${id}`,
    role: 'admin',
    preferences: { theme: 'auto', language: 'en', timezone: 'UTC' },
    createdAt: new Date('2026-01-01T00:00:00Z'),
  }
}

function applyDefaultMocks() {
  vi.mocked(useI18n).mockReturnValue({ t: stubT } as unknown as ReturnType<typeof useI18n>)
  vi.mocked(ApiClient.get).mockResolvedValue({})
  vi.mocked(ApiClient.post).mockResolvedValue({})
}

function mountPanel(pinia: Pinia) {
  return mount(KnowledgeResearchPanel, {
    global: {
      plugins: [pinia],
      mocks: { $t: stubT },
      stubs: {
        InteractiveScreenshot: true,
      },
    },
  })
}

/** Flush pending microtasks so onMounted async work settles. */
const flushAsync = () => new Promise((resolve) => setTimeout(resolve, 0))

function statusUrlFor(call: unknown[]): string {
  return call[0] as string
}

describe('KnowledgeResearchPanel — visual-browser proxy session isolation (#11925)', () => {
  let pinia: Pinia

  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    vi.clearAllMocks()
    applyDefaultMocks()
  })

  it('derives DIFFERENT worker-status session ids for two different users', async () => {
    const userStore = useUserStore()
    userStore.login(makeUser('alice'), { token: 't' })
    const wrapperA = mountPanel(pinia)
    await flushAsync()
    const urlA = statusUrlFor(vi.mocked(ApiClient.get).mock.calls[0])
    wrapperA.unmount()

    const piniaB = createPinia()
    setActivePinia(piniaB)
    vi.clearAllMocks()
    applyDefaultMocks()
    const userStoreB = useUserStore()
    userStoreB.login(makeUser('bob'), { token: 't' })
    const wrapperB = mountPanel(piniaB)
    await flushAsync()
    const urlB = statusUrlFor(vi.mocked(ApiClient.get).mock.calls[0])
    wrapperB.unmount()

    expect(urlA).toContain('session_id=knowledge-research-alice')
    expect(urlB).toContain('session_id=knowledge-research-bob')
    expect(urlA).not.toBe(urlB)
  })

  it('keeps the SAME user stable across worker-status and worker-screenshot calls', async () => {
    // Worker reports connected so the screenshot-refresh button isn't disabled.
    vi.mocked(ApiClient.get).mockResolvedValue({ status: 'connected', browser_connected: true })

    const userStore = useUserStore()
    userStore.login(makeUser('alice'), { token: 't' })
    const wrapper = mountPanel(pinia)
    await flushAsync()

    const statusUrl = statusUrlFor(vi.mocked(ApiClient.get).mock.calls[0])
    expect(statusUrl).toContain('session_id=knowledge-research-alice')

    await wrapper.vm.$nextTick()
    const refreshBtn = wrapper.find('.screenshot-refresh-btn')
    await refreshBtn.trigger('click')
    await flushAsync()

    const screenshotCall = vi.mocked(ApiClient.post).mock.calls.find(
      (call) => (call[0] as string).includes('worker-screenshot')
    )
    expect(screenshotCall).toBeDefined()
    expect((screenshotCall as unknown[])[1]).toMatchObject({
      session_id: 'knowledge-research-alice',
    })
  })

  it('omits session_id (shared default bucket) when no user is authenticated', async () => {
    mountPanel(pinia)
    await flushAsync()

    const statusUrl = statusUrlFor(vi.mocked(ApiClient.get).mock.calls[0])
    expect(statusUrl).not.toContain('session_id=')
  })
})
