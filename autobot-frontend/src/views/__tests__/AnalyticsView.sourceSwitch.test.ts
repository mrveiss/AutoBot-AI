// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #21474: a source switch re-targets the codebase project route with another `:sourceId`. Vue reuses
// a routed component across a param change, so the page kept the previous source's results. The
// analytics view keys its routed page by the source, so a switch remounts it exactly as a page open.
//
// The REAL route records from `@/router` (paths, names, nesting, and AnalyticsView as the parent);
// only the project page and its sub-tab views are swapped for probes that count their mounts.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'
import { createMemoryHistory, createRouter, RouterView, type RouteRecordRaw } from 'vue-router'
import { defineComponent, h, onMounted } from 'vue'
import en from '@/i18n/locales/en.json'

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get: () => Promise.resolve([]) }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: () => undefined, error: () => undefined, info: () => undefined, debug: () => undefined }),
}))

import { routes } from '@/router'
import AnalyticsView from '../AnalyticsView.vue'

const PROJECT = 'analytics-codebase-project'
const SUB_TABS = [
  'analytics-codebase-code-quality',
  'analytics-codebase-code-review',
  'analytics-codebase-evolution',
  'analytics-codebase-code-generation',
]
const mounts = { page: 0, subTab: 0 }

const probe = (key: 'page' | 'subTab') =>
  defineComponent({
    setup() {
      onMounted(() => {
        mounts[key] += 1
      })
      return () => h('div', key === 'page' ? [h(RouterView)] : [])
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

/** The real record, with the project page and its sub-tabs swapped for probes. */
function withProbes(record: RouteRecordRaw): RouteRecordRaw {
  const children = record.children?.map(withProbes)
  if (record.name === PROJECT) return { ...record, component: probe('page'), children } as RouteRecordRaw
  if (SUB_TABS.includes(String(record.name))) return { ...record, component: probe('subTab') } as RouteRecordRaw
  return { ...record, ...(children ? { children } : {}) } as RouteRecordRaw
}

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

async function mountAt(name: string, sourceId: string) {
  mounts.page = 0
  mounts.subTab = 0
  const router = createRouter({ history: createMemoryHistory(), routes: [withProbes(findRecord('analytics')!)] })
  await router.push({ name, params: { sourceId } })
  await router.isReady()
  mount({ render: () => h(RouterView) }, { global: { plugins: [router, i18n] } })
  await flushPromises()
  return router
}

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('the real analytics routes (#21474)', () => {
  it('the project page and its sub-tabs live under AnalyticsView at codebase/:sourceId', () => {
    const analytics = findRecord('analytics')!
    const project = findRecord(PROJECT)!
    expect(analytics.component).toBe(AnalyticsView)
    expect(analytics.children).toContain(project)
    expect(project.path).toBe('codebase/:sourceId')
    expect(project.children?.map((r) => r.name)).toEqual(SUB_TABS)
  })
})

describe('the analytics view remounts the project page on a source switch (#21474)', () => {
  it('a switch to another source mounts the page again', async () => {
    const router = await mountAt(PROJECT, 'source-a')
    expect(mounts.page).toBe(1)

    await router.push({ name: PROJECT, params: { sourceId: 'source-b' } })
    await flushPromises()

    expect(mounts.page).toBe(2)
  })

  it.each(SUB_TABS)('a switch on the %s sub-tab remounts the page and the sub-tab', async (subTab) => {
    const router = await mountAt(subTab, 'source-a')
    expect(mounts).toEqual({ page: 1, subTab: 1 })

    await router.push({ name: subTab, params: { sourceId: 'source-b' } })
    await flushPromises()

    expect(mounts).toEqual({ page: 2, subTab: 2 })
  })

  it('moving between sub-tabs of the same source keeps the page mounted', async () => {
    const router = await mountAt(PROJECT, 'source-a')

    await router.push({ name: SUB_TABS[0], params: { sourceId: 'source-a' } })
    await flushPromises()

    expect(mounts).toEqual({ page: 1, subTab: 1 })
  })
})
