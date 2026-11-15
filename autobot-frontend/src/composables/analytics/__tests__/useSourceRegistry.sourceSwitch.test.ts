// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Selecting another source navigates to its page (#21474).
 *
 * The selection used to swap the source in place, so every section kept the previous source's
 * results. It is now a navigation on the current route with the new `:sourceId`; the analytics
 * view keys the page by that param and remounts it (`AnalyticsView.sourceSwitch.test.ts`).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { reactive } from 'vue'
import type { CodeSource } from '@/types/analytics'

const push = vi.fn()
const route = reactive({ name: 'analytics-codebase-code-quality', params: { sourceId: 'source-a' } as Record<string, string> })

vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ push: (...args: unknown[]) => push(...args) }),
}))
vi.mock('@/utils/ApiClient', () => ({ default: { get: () => Promise.resolve({}), post: () => Promise.resolve({}), put: () => Promise.resolve({}) } }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ info: () => undefined, warn: () => undefined, error: () => undefined, debug: () => undefined }),
}))

import { useSourceRegistry } from '../useSourceRegistry'

const source = (id: string): CodeSource => ({ id, name: `Source ${id}`, clone_path: `/clones/${id}` }) as CodeSource

const registry = () => useSourceRegistry({ t: (key: string) => key, showToast: () => undefined, notify: () => undefined })

beforeEach(() => {
  route.name = 'analytics-codebase-code-quality'
  route.params = { sourceId: 'source-a' }
})

describe('handleSelectSource (#21474)', () => {
  it('another source is a navigation to its page on the current sub-tab, not an in-place swap', () => {
    push.mockResolvedValue(undefined)
    const r = registry()
    r.showSourceManager.value = true
    const rootBefore = r.rootPath.value

    r.handleSelectSource(source('source-b'))

    expect(push).toHaveBeenCalledWith({ name: 'analytics-codebase-code-quality', params: { sourceId: 'source-b' } })
    expect(r.selectedSource.value).toBeNull()
    expect(r.rootPath.value).toBe(rootBefore)
    expect(r.showSourceManager.value).toBe(false)
  })

  it('the source already shown is selected in place, with no navigation', () => {
    push.mockResolvedValue(undefined)
    const r = registry()

    r.handleSelectSource(source('source-a'))

    expect(push).not.toHaveBeenCalled()
    expect(r.selectedSource.value?.id).toBe('source-a')
    expect(r.rootPath.value).toBe('/clones/source-a')
  })
})
