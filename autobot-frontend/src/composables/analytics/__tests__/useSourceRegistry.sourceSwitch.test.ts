// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Selecting another source navigates to its page (#21474).
 *
 * The selection used to swap the source in place, so every section kept the previous source's
 * results. It is now a navigation on the current route with the new `:sourceId` (query and hash
 * kept); the analytics view keys the page by that param and remounts it
 * (`AnalyticsView.sourceSwitch.test.ts`). The "selected" toast follows a navigation that landed.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { reactive } from 'vue'
import type { CodeSource } from '@/types/analytics'

const push = vi.fn()
const route = reactive({
  name: 'analytics-codebase-code-quality',
  params: { sourceId: 'source-a' } as Record<string, string>,
  query: {} as Record<string, string>,
  hash: '',
})

vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ push: (...args: unknown[]) => push(...args) }),
}))
const fetchWithAuth = vi.fn()
vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth: (...a: unknown[]) => fetchWithAuth(...a) }))
vi.mock('@/config/AppConfig.js', () => ({ default: { getServiceUrl: () => Promise.resolve('http://backend') } }))
vi.mock('@/utils/ApiClient', () => ({ default: { get: () => Promise.resolve({}), post: () => Promise.resolve({}), put: () => Promise.resolve({}) } }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ info: () => undefined, warn: () => undefined, error: () => undefined, debug: () => undefined }),
}))

import { useSourceRegistry } from '../useSourceRegistry'

const source = (id: string): CodeSource => ({ id, name: `Source ${id}`, clone_path: `/clones/${id}` }) as CodeSource

const registry = (notify: (msg: string) => void) =>
  useSourceRegistry({ t: (key: string) => key, showToast: () => undefined, notify })

beforeEach(() => {
  route.name = 'analytics-codebase-code-quality'
  route.params = { sourceId: 'source-a' }
  route.query = { tab: 'smells' }
  route.hash = '#duplicates'
})

describe('handleSelectSource (#21474)', () => {
  it('another source is a navigation to its page on the current sub-tab, query and hash, not an in-place swap', async () => {
    push.mockResolvedValue(undefined)
    const notify = vi.fn()
    const r = registry(notify)
    r.showSourceManager.value = true
    const rootBefore = r.rootPath.value

    await r.handleSelectSource(source('source-b'))

    expect(push).toHaveBeenCalledWith({
      name: 'analytics-codebase-code-quality',
      params: { sourceId: 'source-b' },
      query: { tab: 'smells' },
      hash: '#duplicates',
    })
    expect(r.selectedSource.value).toBeNull()
    expect(r.rootPath.value).toBe(rootBefore)
    expect(r.showSourceManager.value).toBe(false)
    expect(notify).toHaveBeenCalledWith('analytics.codebase.notify.selectedSource', 'info')
  })

  it('the "selected" toast waits for the navigation: none while it is pending', async () => {
    let land!: () => void
    push.mockReturnValue(new Promise<void>((resolve) => { land = resolve }))
    const notify = vi.fn()
    const r = registry(notify)

    const selecting = r.handleSelectSource(source('source-b'))
    await Promise.resolve()
    expect(notify).not.toHaveBeenCalled()

    land()
    await selecting
    expect(notify).toHaveBeenCalledTimes(1)
  })

  it('a navigation that did not land (blocked, aborted or failed) says nothing was selected', async () => {
    const notify = vi.fn()
    const r = registry(notify)

    push.mockResolvedValue(Object.assign(new Error('Navigation aborted'), { type: 4 }))
    await r.handleSelectSource(source('source-b'))
    push.mockRejectedValue(new Error('guard threw'))
    await r.handleSelectSource(source('source-c'))

    expect(push).toHaveBeenCalledTimes(2)
    expect(notify).not.toHaveBeenCalled()
  })

  it('a source read answered after the page was left saves no path and selects nothing', async () => {
    const respond = { ok: true, status: 200, json: async () => source('source-a'), text: async () => '{}' }
    let answer!: () => void
    fetchWithAuth.mockImplementation(() => new Promise((resolve) => { answer = () => resolve(respond) }))
    const notify = vi.fn()
    const r = registry(notify)
    localStorage.setItem('codebase-analytics-path', '/clones/the-next-page')
    let open = true

    const loading = r.loadSourceById('source-a', () => open)
    await vi.waitFor(() => expect(fetchWithAuth).toHaveBeenCalled())
    open = false // the page was left (a source switch remounted it)
    answer()

    expect(await loading).toBe(false)
    expect(localStorage.getItem('codebase-analytics-path')).toBe('/clones/the-next-page')
    expect(r.selectedSource.value).toBeNull()
    expect(notify).not.toHaveBeenCalled()
  })

  it('control: the same answer on an open page selects the source and saves its path', async () => {
    fetchWithAuth.mockResolvedValue({ ok: true, status: 200, json: async () => source('source-a'), text: async () => '{}' })
    const r = registry(vi.fn())

    expect(await r.loadSourceById('source-a', () => true)).toBe(true)
    expect(localStorage.getItem('codebase-analytics-path')).toBe('/clones/source-a')
    expect(r.selectedSource.value?.id).toBe('source-a')
  })

  it('the source already shown is selected in place, with no navigation', async () => {
    push.mockResolvedValue(undefined)
    const notify = vi.fn()
    const r = registry(notify)

    await r.handleSelectSource(source('source-a'))

    expect(push).not.toHaveBeenCalled()
    expect(r.selectedSource.value?.id).toBe('source-a')
    expect(r.rootPath.value).toBe('/clones/source-a')
    expect(notify).toHaveBeenCalledTimes(1)
  })
})
