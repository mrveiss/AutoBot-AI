// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Tests for KnowledgeHealth.vue — tab shell for /knowledge/health (#11558).
 *
 * Covers:
 *  - Default mount renders the analytics tab active
 *  - ?tab=tools deep link activates the tools tab from the FIRST render
 *    (activeTab is initialized from the route at setup time, not onMounted)
 *  - Bogus ?tab= values fall back to analytics
 *  - Verification badge renders when store.pendingVerificationsTotal > 0
 *    and is hidden at 0
 *  - Badge prefetch uses the total-only setter and never clobbers a
 *    pending-verifications list another component already loaded
 *
 * NOTE: vitest.config has mockReset: true which clears vi.mock() factory
 * implementations between tests. All mock implementations are re-applied in
 * beforeEach.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { ref } from 'vue'
import type { PendingSource } from '@/types/knowledgeBase'

// ── Module-level mocks (hoisted by Vitest) ───────────────────────────────────

vi.mock('vue-router', () => ({
  useRoute: vi.fn(),
  useRouter: vi.fn(),
}))

vi.mock('@/models/repositories/KnowledgeRepository', () => ({
  knowledgeRepository: {
    getPendingVerifications: vi.fn(),
  },
}))

vi.mock('@/composables/knowledge/useKnowledgeMaintenance', () => ({
  useKnowledgeMaintenance: vi.fn(),
}))

vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
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

// Shallow stubs for the heavy tab children — keeps the shell test light
vi.mock('@/components/knowledge/KnowledgeHealthAnalytics.vue', () => ({
  default: { name: 'KnowledgeHealthAnalytics', template: '<div data-testid="analytics-tab" />' },
}))
vi.mock('@/components/knowledge/KnowledgeVerificationQueue.vue', () => ({
  default: { name: 'KnowledgeVerificationQueue', template: '<div data-testid="verification-tab" />' },
}))
vi.mock('@/components/knowledge/KnowledgeHealthTools.vue', () => ({
  default: { name: 'KnowledgeHealthTools', template: '<div data-testid="tools-tab" />' },
}))

// ── Imports after mocks ──────────────────────────────────────────────────────

import { useRoute } from 'vue-router'
import { knowledgeRepository } from '@/models/repositories/KnowledgeRepository'
import { useKnowledgeMaintenance } from '@/composables/knowledge/useKnowledgeMaintenance'
import ApiClient from '@/utils/ApiClient'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import KnowledgeHealth from '../KnowledgeHealth.vue'

// ── Helpers ──────────────────────────────────────────────────────────────────

const stubT = (key: string, _params?: object) => key

function makePendingSource(id: string): PendingSource {
  return {
    fact_id: id,
    content: `content-${id}`,
    source_type: 'web',
    quality_score: 0.9,
    timestamp: '2026-07-10T00:00:00Z',
    domain: null,
    title: null,
    url: null,
  }
}

function setRouteQuery(query: Record<string, string>) {
  vi.mocked(useRoute).mockReturnValue({ query } as unknown as ReturnType<typeof useRoute>)
}

function applyDefaultMocks() {
  setRouteQuery({})
  vi.mocked(useKnowledgeMaintenance).mockReturnValue({
    healthDashboard: ref(null),
    isLoadingHealth: ref(false),
    healthError: ref(''),
    loadHealthDashboard: vi.fn().mockResolvedValue(undefined),
  } as unknown as ReturnType<typeof useKnowledgeMaintenance>)
  vi.mocked(knowledgeRepository.getPendingVerifications).mockResolvedValue({
    sources: [],
    total: 0,
    page: 1,
  })
  // store.refreshStats() (called by the shell's loadVectorHealth) goes through
  // ApiClient — resolve with a minimal stats payload so no network is hit.
  vi.mocked(ApiClient.get).mockResolvedValue({})
}

function mountHealth(pinia: Pinia) {
  return mount(KnowledgeHealth, {
    global: {
      plugins: [pinia],
      mocks: { $t: stubT },
      stubs: {
        Icon: true,
        BaseButton: true,
      },
    },
  })
}

/** Flush pending microtasks so onMounted async work settles. */
const flushAsync = () => new Promise((resolve) => setTimeout(resolve, 0))

// ── Tests ────────────────────────────────────────────────────────────────────

describe('KnowledgeHealth — tab initialization from route (#11558)', () => {
  let pinia: Pinia

  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    applyDefaultMocks()
  })

  it('renders the analytics tab active by default (no ?tab= param)', () => {
    const wrapper = mountHealth(pinia)
    expect(wrapper.find('[data-testid="analytics-tab"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="verification-tab"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="tools-tab"]').exists()).toBe(false)
  })

  it('activates the tools tab from the route on FIRST render (?tab=tools)', () => {
    setRouteQuery({ tab: 'tools' })
    const wrapper = mountHealth(pinia)
    // Asserted synchronously before onMounted async work — the deep-linked tab
    // must be the first (and only) tab child ever mounted, no analytics flash.
    expect(wrapper.find('[data-testid="tools-tab"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="analytics-tab"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="verification-tab"]').exists()).toBe(false)
  })

  it('falls back to analytics when ?tab= is not a known tab id', () => {
    setRouteQuery({ tab: 'bogus' })
    const wrapper = mountHealth(pinia)
    expect(wrapper.find('[data-testid="analytics-tab"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="tools-tab"]').exists()).toBe(false)
  })
})

describe('KnowledgeHealth — verification badge', () => {
  let pinia: Pinia

  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    applyDefaultMocks()
  })

  it('shows the badge when pendingVerificationsTotal > 0', async () => {
    const wrapper = mountHealth(pinia)
    await flushAsync() // let the onMounted prefetch (total 0) settle first
    const store = useKnowledgeStore()
    store.setPendingVerificationsTotal(7)
    await wrapper.vm.$nextTick()
    const badge = wrapper.find('.tab-badge')
    expect(badge.exists()).toBe(true)
    expect(badge.text()).toBe('7')
  })

  it('hides the badge when pendingVerificationsTotal is 0', async () => {
    const wrapper = mountHealth(pinia)
    await flushAsync()
    expect(useKnowledgeStore().pendingVerificationsTotal).toBe(0)
    expect(wrapper.find('.tab-badge').exists()).toBe(false)
  })
})

describe('KnowledgeHealth — badge prefetch uses the total-only setter (#11558)', () => {
  let pinia: Pinia

  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    applyDefaultMocks()
  })

  it('updates the total without clobbering an already-loaded list', async () => {
    // KnowledgeVerificationQueue (deep link) already loaded page 1 (20 items)
    const store = useKnowledgeStore()
    const existing = Array.from({ length: 20 }, (_, i) => makePendingSource(`fact-${i}`))
    store.setPendingVerifications(existing, 20)

    // The shell's badge prefetch resolves later with a 1-item page
    vi.mocked(knowledgeRepository.getPendingVerifications).mockResolvedValue({
      sources: [makePendingSource('prefetch-only')],
      total: 99,
      page: 1,
    })

    setRouteQuery({ tab: 'verification' })
    mountHealth(pinia)
    await flushAsync()

    // List untouched; only the total was updated by the prefetch
    expect(store.pendingVerifications).toHaveLength(20)
    expect(store.pendingVerifications[0].fact_id).toBe('fact-0')
    expect(store.pendingVerificationsTotal).toBe(99)
    expect(knowledgeRepository.getPendingVerifications).toHaveBeenCalledWith(1, 1)
  })
})
