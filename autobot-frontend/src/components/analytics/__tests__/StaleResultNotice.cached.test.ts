// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * A cached result older than the source's last sync is shown with a notice saying so (#17982):
 * the real fetchers load the cached routes, the real notice reads what they flagged.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { computed, defineComponent, h, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const fetchWithAuth = vi.fn()
vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth: (...a: unknown[]) => fetchWithAuth(...a) }))
vi.mock('@/config/AppConfig.js', () => ({
  default: { getServiceUrl: vi.fn(async () => 'http://backend'), getApiUrl: vi.fn(async () => 'http://backend/api') },
}))

import { useAnalyticsDataFetchers } from '@/composables/analytics/useAnalyticsDataFetchers'
import StaleResultNotice from '../StaleResultNotice.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const respond = (body: unknown) => ({ ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) })
const ROW = { file1: 'a', file2: 'b', similarity: 90, lines: 4 }
const NOTICE = '[data-testid="stale-result-notice"]'

type Fetchers = ReturnType<typeof useAnalyticsDataFetchers>

function host() {
  const captured: { fetchers?: Fetchers } = {}
  const Host = defineComponent({
    setup() {
      captured.fetchers = useAnalyticsDataFetchers({
        rootPath: ref('/repo'),
        sourceIdQuery: computed(() => ({ source_id: 's1' })),
        withSourceId: (url: string) => `${url}${url.includes('?') ? '&' : '?'}source_id=s1`,
        t: (key: string) => key,
        showToast: vi.fn(),
        notify: vi.fn(),
      } as unknown as Parameters<typeof useAnalyticsDataFetchers>[0])
      return () => [
        h(StaleResultNotice, { kind: 'duplicates' }),
        h(StaleResultNotice, { kind: 'dependencies' }),
        h(StaleResultNotice, { kind: 'importTree' }),
      ]
    },
  })
  const wrapper = mount(Host, { global: { plugins: [i18n] } })
  return { wrapper, fetchers: captured.fetchers as Fetchers }
}

describe('stale cached results (#17982)', () => {
  beforeEach(() => {
    fetchWithAuth.mockReset()
  })

  it('cached duplicates flagged stale show the notice; a full scan clears it', async () => {
    fetchWithAuth.mockResolvedValue(respond({ status: 'success', from_cache: true, stale: true, duplicates: [ROW] }))
    const { wrapper, fetchers } = host()
    await fetchers.loadCachedDuplicates()
    await flushPromises()
    expect(wrapper.findAll(NOTICE)).toHaveLength(1)
    expect(wrapper.text()).toContain(en.analytics.codebase.staleResult.message)
    expect(fetchers.duplicateAnalysis.value).toHaveLength(1) // served, not hidden

    fetchWithAuth.mockResolvedValue(respond({ status: 'success', duplicates: [ROW] }))
    await fetchers.getDuplicatesData()
    await flushPromises()
    expect(wrapper.find(NOTICE).exists()).toBe(false)
  })

  it('cached duplicates that are current show no notice', async () => {
    fetchWithAuth.mockResolvedValue(respond({ status: 'success', from_cache: true, stale: false, duplicates: [ROW] }))
    const { wrapper, fetchers } = host()
    await fetchers.loadCachedDuplicates()
    await flushPromises()
    expect(wrapper.find(NOTICE).exists()).toBe(false)
  })

  it('stale cached dependencies and import tree are each flagged', async () => {
    fetchWithAuth.mockImplementation(async (url: string) =>
      respond(
        url.includes('/dependencies/cached')
          ? { status: 'success', stale: true, dependency_data: { nodes: [], edges: [] } }
          : { status: 'success', stale: true, import_tree: [{ name: 'm', path: 'm.py' }] },
      ),
    )
    const { wrapper, fetchers } = host()
    await fetchers.loadCachedDependencies()
    await fetchers.loadCachedImportTree()
    await flushPromises()
    expect(wrapper.findAll(NOTICE)).toHaveLength(2)
    expect(fetchers.dependencyData.value).not.toBeNull()
    expect(fetchers.importTreeData.value).toHaveLength(1)
  })
})
