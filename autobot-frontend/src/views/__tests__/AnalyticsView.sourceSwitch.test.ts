// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #21474: a source switch re-targets the codebase project route with another `:sourceId`. Vue reuses
// a routed component across a param change, so the page kept the previous source's results. The
// analytics view keys its routed page by the source, so a switch remounts it exactly as a page open.
//
// A real router and the real AnalyticsView; the routed page and its sub-tab are probes that count
// their mounts.

import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { defineComponent, h, onMounted } from 'vue'
import en from '@/i18n/locales/en.json'

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: () => undefined, error: () => undefined, info: () => undefined, debug: () => undefined }),
}))

import AnalyticsView from '../AnalyticsView.vue'

const mounts = { page: 0, subTab: 0 }

const page = defineComponent({
  setup() {
    onMounted(() => {
      mounts.page += 1
    })
    return () => h('div', [h(RouterView)])
  },
})

const subTab = defineComponent({
  setup() {
    onMounted(() => {
      mounts.subTab += 1
    })
    return () => h('section')
  },
})

function buildRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/analytics',
        component: AnalyticsView,
        children: [
          {
            path: 'codebase/:sourceId',
            name: 'analytics-codebase-project',
            component: page,
            children: [{ path: 'code-quality', name: 'analytics-codebase-code-quality', component: subTab }],
          },
        ],
      },
    ],
  })
}

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

async function mountAt(name: string, sourceId: string) {
  mounts.page = 0
  mounts.subTab = 0
  const router = buildRouter()
  await router.push({ name, params: { sourceId } })
  await router.isReady()
  mount({ render: () => h(RouterView) }, { global: { plugins: [router, i18n] } })
  await flushPromises()
  return router
}

describe('the analytics view remounts the project page on a source switch (#21474)', () => {
  it('a switch to another source mounts the page again', async () => {
    const router = await mountAt('analytics-codebase-project', 'source-a')
    expect(mounts.page).toBe(1)

    await router.push({ name: 'analytics-codebase-project', params: { sourceId: 'source-b' } })
    await flushPromises()

    expect(mounts.page).toBe(2)
  })

  it('a switch on a sub-tab remounts the page and the sub-tab', async () => {
    const router = await mountAt('analytics-codebase-code-quality', 'source-a')
    expect(mounts).toEqual({ page: 1, subTab: 1 })

    await router.push({ name: 'analytics-codebase-code-quality', params: { sourceId: 'source-b' } })
    await flushPromises()

    expect(mounts).toEqual({ page: 2, subTab: 2 })
  })

  it('moving between sub-tabs of the same source keeps the page mounted', async () => {
    const router = await mountAt('analytics-codebase-project', 'source-a')

    await router.push({ name: 'analytics-codebase-code-quality', params: { sourceId: 'source-a' } })
    await flushPromises()

    expect(mounts).toEqual({ page: 1, subTab: 1 })
  })
})
