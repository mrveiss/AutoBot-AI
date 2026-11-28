// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #21474 AC2: a late answer for the previous source must not write into the new source's page.
//
// The REAL analytics route records and AnalyticsView (which keys the routed page by its source);
// only the project page is swapped for a page that calls the REAL `useAnalyticsDataFetchers` the way
// CodebaseAnalytics does (route-derived source, page-local state) and prints what it holds. The
// network is held: every request of source A stays pending across the switch, then is answered.
// The mock ignores the AbortSignal, so the answer reaches its handler -- the worst case.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'
import { createMemoryHistory, createRouter, RouterView, useRoute, type RouteRecordRaw } from 'vue-router'
import { computed, defineComponent, h, onMounted, ref } from 'vue'
import en from '@/i18n/locales/en.json'

interface Held {
  url: string
  settle: (body: unknown) => void
}
const held: Held[] = []

vi.mock('@/utils/fetchWithAuth', () => ({
  fetchWithAuth: (url: string) =>
    new Promise((resolve) => {
      held.push({
        url,
        settle: (body) => resolve({ ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) }),
      })
    }),
}))
vi.mock('@/config/AppConfig.js', () => ({
  default: { getServiceUrl: () => Promise.resolve('http://backend'), getApiUrl: () => Promise.resolve('http://backend/api') },
}))
vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get: () => Promise.resolve([]) }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: () => undefined, error: () => undefined, info: () => undefined, debug: () => undefined }),
}))

import { routes } from '@/router'
import { useAnalyticsDataFetchers } from '@/composables/analytics/useAnalyticsDataFetchers'

const PROJECT = 'analytics-codebase-project'
const mounts = { page: 0 }

/** What the backend answers for `source`: every value carries the source's name. */
function answerFor(url: string, source: string): unknown {
  const tag = `of-${source}`
  if (url.includes('/duplicates/cached')) {
    return { status: 'success', duplicates: [{ file1: `dup-${tag}.py`, file2: 'x.py', similarity: 90, lines: 5 }] }
  }
  if (url.includes('/dependencies/cached')) {
    return { status: 'success', dependency_data: { nodes: [{ id: `dep-${tag}` }], edges: [] } }
  }
  if (url.includes('/import-tree/cached')) {
    return { status: 'success', import_tree: [{ name: `imp-${tag}` }] }
  }
  if (url.includes('/codebase/stats')) return { status: 'success', stats: { marker: `stats-${tag}` } }
  if (url.includes('/codebase/problems')) {
    return { status: 'success', problems: [{ severity: 'low', type: 't', message: `problem-${tag}`, file_path: 'f.py' }] }
  }
  if (url.includes('/codebase/declarations')) {
    return { status: 'success', declarations: [{ type: 'function', name: `decl-${tag}`, file_path: 'f.py' }] }
  }
  return { status: 'no_data' }
}

/** The project page: the real fetchers, the real route-derived source, the loads a page open runs. */
const ProjectPage = defineComponent({
  setup() {
    mounts.page += 1
    const route = useRoute()
    const sourceId = () => route.params.sourceId as string
    const f = useAnalyticsDataFetchers({
      rootPath: ref('/repo'),
      sourceIdParam: computed(() => `source_id=${sourceId()}`),
      sourceIdQuery: computed(() => ({ source_id: sourceId() })),
      withSourceId: (url: string) => `${url}${url.includes('?') ? '&' : '?'}source_id=${sourceId()}`,
      analyzing: ref(false),
      t: (key: string) => key,
      showToast: () => undefined,
      notify: () => undefined,
    })
    onMounted(() => {
      void f.getCodebaseStats()
      void f.getProblemsReport()
      void f.loadDeclarations()
      void f.loadCachedDuplicates()
      void f.loadCachedDependencies()
      void f.loadCachedImportTree()
    })
    return () =>
      h('pre', JSON.stringify({
        stats: f.codebaseStats.value,
        problems: f.problemsReport.value,
        declarations: f.declarationAnalysis.value,
        duplicates: f.duplicateAnalysis.value,
        dependencies: f.dependencyData.value,
        importTree: f.importTreeData.value,
      }))
  },
})

function findRecord(name: string, list: RouteRecordRaw[] = routes): RouteRecordRaw | undefined {
  for (const record of list) {
    if (record.name === name) return record
    const found = record.children ? findRecord(name, record.children) : undefined
    if (found) return found
  }
  return undefined
}

/** The real record, with only the project page swapped. */
function withPage(record: RouteRecordRaw): RouteRecordRaw {
  const children = record.children?.map(withPage)
  if (record.name === PROJECT) return { ...record, component: ProjectPage, children } as RouteRecordRaw
  return { ...record, ...(children ? { children } : {}) } as RouteRecordRaw
}

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

async function mountAt(sourceId: string) {
  mounts.page = 0
  held.length = 0
  const router = createRouter({ history: createMemoryHistory(), routes: [withPage(findRecord('analytics')!)] })
  await router.push({ name: PROJECT, params: { sourceId } })
  await router.isReady()
  const wrapper = mount({ render: () => h(RouterView) }, { global: { plugins: [router, i18n] } })
  await flushPromises()
  return { router, wrapper }
}

/** Answer every held request made for `source`; returns how many were answered. */
async function answer(source: string): Promise<number> {
  const mine = held.filter((r) => r.url.includes(`source_id=${source}`))
  mine.forEach((r) => r.settle(answerFor(r.url, source)))
  await flushPromises()
  return mine.length
}

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('a late answer for the previous source (#21474 AC2)', () => {
  it('control: the same answers, released WITHOUT a switch, land in the page', async () => {
    const { wrapper } = await mountAt('source-a')
    expect(wrapper.text()).not.toContain('of-source-a')

    expect(await answer('source-a')).toBeGreaterThanOrEqual(6)

    const text = wrapper.text()
    for (const marker of ['stats-', 'problem-', 'decl-', 'dup-', 'dep-', 'imp-']) {
      expect(text).toContain(`${marker}of-source-a`)
    }
  })

  it('switching to B and then answering A leaves none of A in B\'s page (A answered after B)', async () => {
    const { router, wrapper } = await mountAt('source-a')
    await router.push({ name: PROJECT, params: { sourceId: 'source-b' } })
    await flushPromises()
    expect(mounts.page).toBe(2)

    expect(await answer('source-b')).toBeGreaterThanOrEqual(6)
    expect(wrapper.text()).toContain('stats-of-source-b')

    expect(await answer('source-a')).toBeGreaterThanOrEqual(6)

    const text = wrapper.text()
    expect(text).not.toContain('source-a')
    for (const marker of ['stats-', 'problem-', 'decl-', 'dup-', 'dep-', 'imp-']) {
      expect(text).toContain(`${marker}of-source-b`)
    }
  })

  it('switching to B and answering A BEFORE B shows none of A, before and after B answers', async () => {
    const { router, wrapper } = await mountAt('source-a')
    await router.push({ name: PROJECT, params: { sourceId: 'source-b' } })
    await flushPromises()

    expect(await answer('source-a')).toBeGreaterThanOrEqual(6)
    expect(wrapper.text()).not.toContain('source-a')
    expect(wrapper.text()).not.toContain('of-source-b')

    expect(await answer('source-b')).toBeGreaterThanOrEqual(6)
    expect(wrapper.text()).not.toContain('source-a')
    expect(wrapper.text()).toContain('stats-of-source-b')
  })
})
