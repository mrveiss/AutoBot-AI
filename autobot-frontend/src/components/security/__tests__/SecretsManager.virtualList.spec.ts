// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Component tests for SecretsManager's credential list rendering.
 *
 * Issue #16513: #16486 moved the credentials list onto `useVirtualList`
 * (`displayedSecrets`) and nothing covered that wiring, so a regression that
 * bypassed the virtual list -- or dropped the filter on the way to it --
 * would have rendered a plausible-looking list and passed every test.
 *
 * What is asserted here is the seam, not `useVirtualList`'s own maths (that
 * has its own tests): the FILTERED set is what reaches `displayedSecrets`,
 * list mode positions each row from the virtual item's offset, and grid mode
 * renders the same filtered set unpositioned.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

// ── Module-level mocks (hoisted) ─────────────────────────────────────────────

const getSecrets = vi.fn()
const getSecretsStats = vi.fn()

vi.mock('@/utils/SecretsApiClient', () => ({
  secretsApiClient: {
    getSecrets: (...args: unknown[]) => getSecrets(...args),
    getSecretsStats: (...args: unknown[]) => getSecretsStats(...args),
  },
}))

vi.mock('@/composables/security/useSecretsInfraApi', () => ({
  useSecretsInfraApi: () => ({
    fetchInfraHosts: vi.fn().mockResolvedValue({ hosts: [] }),
    fetchSecretsUsage: vi.fn().mockResolvedValue({}),
    deleteInfraHost: vi.fn().mockResolvedValue(undefined),
  }),
}))

vi.mock('@/stores/useUserStore', () => ({
  useUserStore: () => ({ isAdmin: false }),
}))

vi.mock('@/stores/useChatStore', () => ({
  useChatStore: () => ({ currentSessionId: null }),
}))

// ── Imports after mocks ──────────────────────────────────────────────────────

import SecretsManager from '../SecretsManager.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages: { en: {} },
  missingWarn: false,
  fallbackWarn: false,
})

/** Three credentials of two types -- enough for a filter to narrow the set. */
const SECRETS = [
  { id: 's1', name: 'deploy-key', type: 'ssh_key', scope: 'general' },
  { id: 's2', name: 'openai-key', type: 'api_key', scope: 'general' },
  { id: 's3', name: 'backup-key', type: 'ssh_key', scope: 'general' },
]

async function mountManager(): Promise<VueWrapper> {
  const wrapper = mount(SecretsManager, {
    global: {
      plugins: [i18n],
      stubs: {
        Icon: { name: 'Icon', template: '<i class="icon-stub" />', props: ['name'] },
        EmptyState: true,
        LoadingSpinner: true,
        ShareSecretDialog: true,
        BaseModal: true,
      },
    },
  })
  await flushPromises()
  return wrapper
}

const rows = (wrapper: VueWrapper) => wrapper.findAll('.credential-card')
const names = (wrapper: VueWrapper) => rows(wrapper).map(r => r.find('h4').text())

describe('SecretsManager credential list (#16513)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getSecrets.mockResolvedValue({ secrets: SECRETS })
    getSecretsStats.mockResolvedValue({ total_secrets: 3, expired_count: 0, by_type: {}, by_scope: {} })
  })

  it('renders every loaded credential in grid mode, unpositioned', async () => {
    const wrapper = await mountManager()

    expect(names(wrapper)).toEqual(['deploy-key', 'openai-key', 'backup-key'])
    // Grid mode sets offset null, so no row is absolutely positioned.
    expect(rows(wrapper).every(r => !r.attributes('style')?.includes('translateY'))).toBe(true)
  })

  it('positions each row from the virtual list in list mode', async () => {
    const wrapper = await mountManager()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(wrapper.vm as any).viewMode = 'list'
    await flushPromises()

    const styles = rows(wrapper).map(r => r.attributes('style') || '')
    expect(styles.length).toBe(3)
    // Every rendered row carries a virtual-list offset: the rows came from
    // `visibleItems`, not from the raw array.
    expect(styles.every(s => s.includes('translateY(') && s.includes('absolute'))).toBe(true)
    expect(styles[0]).toContain('translateY(0px)')
  })

  it('renders only the filtered credentials, in both modes', async () => {
    const wrapper = await mountManager()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const vm = wrapper.vm as any

    vm.selectedCategory = 'api_key'
    await flushPromises()
    expect(names(wrapper)).toEqual(['openai-key'])

    vm.viewMode = 'list'
    await flushPromises()
    expect(names(wrapper)).toEqual(['openai-key'])

    vm.selectedCategory = 'ssh_key'
    await flushPromises()
    expect(names(wrapper)).toEqual(['deploy-key', 'backup-key'])
  })
})
