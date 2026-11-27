// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #22349: the Files tab requests -- only the newest list or preview request writes state, and a failed delete,
// rename or create-folder rejects so the caller can report it.
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ get: vi.fn(), delete: vi.fn() }))
const fetchWithAuth = vi.hoisted(() => vi.fn())
vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth }))
vi.mock('@/utils/ApiClient', () => ({ default: api }))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api' }))
vi.mock('@/i18n', () => ({ default: { global: { t: (key: string) => key } } }))

import { useFileBrowser } from '../file-browser/useFileBrowser'

const deferred = <T>() => {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((res) => { resolve = res })
  return { promise, resolve }
}
const item = (name: string) => ({ name, path: `/${name}`, is_dir: false }) as never

describe('useFileBrowser request ordering (#22349)', () => {
  beforeEach(() => { api.get.mockReset(); api.delete.mockReset(); fetchWithAuth.mockReset() })

  it('a late list response for an earlier folder does not overwrite the newer one', async () => {
    const root = deferred<{ files: unknown[] }>()
    api.get.mockReturnValueOnce(root.promise).mockResolvedValueOnce({ files: [{ name: 'docs-file' }] })
    const browser = useFileBrowser()
    const first = browser.fetchFiles('/')
    await browser.fetchFiles('/docs')
    root.resolve({ files: [{ name: 'root-file' }] })
    await first
    expect(browser.files.value).toEqual([{ name: 'docs-file' }])
  })

  it('a refresh with no later request still updates the list', async () => {
    api.get.mockResolvedValueOnce({ files: [{ name: 'a' }] })
    const browser = useFileBrowser()
    await browser.fetchFiles('/')
    expect(browser.files.value).toEqual([{ name: 'a' }])
  })

  it('only the newest preview request writes, and a cancel makes a pending one stale', async () => {
    const slow = deferred<Record<string, string>>()
    api.get.mockReturnValueOnce(slow.promise).mockResolvedValueOnce({ type: 'text', content: 'new' })
    const browser = useFileBrowser()
    const first = browser.fetchPreview(item('old'), () => 'T')
    expect(await browser.fetchPreview(item('new'), () => 'T')).toBe(true)
    slow.resolve({ type: 'text', content: 'old' })
    expect(await first).toBe(false)
    expect(browser.previewFile.value?.name).toBe('new')

    const pending = deferred<Record<string, string>>()
    api.get.mockReturnValueOnce(pending.promise)
    const closing = browser.fetchPreview(item('late'), () => 'T')
    browser.cancelPreview()
    pending.resolve({ type: 'text', content: 'late' })
    expect(await closing).toBe(false)
    expect(browser.previewFile.value?.name).toBe('new')
  })

  it('a failed delete, rename and create-folder reject instead of resolving as success', async () => {
    api.delete.mockRejectedValueOnce(new Error('nope'))
    fetchWithAuth.mockResolvedValue(new Response('', { status: 500, statusText: 'Server Error' }))
    const browser = useFileBrowser()
    await expect(browser.deleteFileOrFolder('/a')).rejects.toThrow()
    await expect(browser.renameFileOrFolder('/a', 'b')).rejects.toThrow()
    await expect(browser.createDirectory('/', 'd')).rejects.toThrow()
  })
})
