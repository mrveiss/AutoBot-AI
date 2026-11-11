// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #20906: the preview-pane path of previewFile: fallback to the bytes, latest request wins, stale clear.
import { beforeEach, describe, expect, it, vi } from 'vitest'

const rawRequest = vi.fn()
const get = vi.fn()
const del = vi.fn()
const put = vi.fn()
vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ rawRequest, get, delete: del, put }) }))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api' }))

import { useConversationFiles } from '../useConversationFiles'

const entry = (id: string, mime: string, size = 5) => ({
  file_id: id, filename: `${id}.dat`, original_filename: `${id}.dat`, size, mime_type: mime,
  uploaded_at: '2026-10-31T10:00:00Z', uploaded_by: 'alice',
})
const listing = (...files: ReturnType<typeof entry>[]) => ({ files, total_files: files.length, total_size: 10 })
const body = (content: string | null, available = true) => ({
  file_info: { file_id: 'x' }, preview_available: available, preview_content: content, preview_type: 'text',
})

describe('useConversationFiles preview pane (#20906)', () => {
  let tab: { location: { href: string }; close: ReturnType<typeof vi.fn> }
  const load = async (...files: ReturnType<typeof entry>[]) => {
    get.mockImplementation(async (url: string) => (url.includes('/list') ? listing(...files) : body('hi')))
    const f = useConversationFiles('s1')
    await f.loadFiles()
    return f
  }

  beforeEach(() => {
    vi.clearAllMocks()
    get.mockReset(); rawRequest.mockReset(); del.mockReset(); put.mockReset()
    tab = { location: { href: '' }, close: vi.fn() }
    vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window)
    window.URL.createObjectURL = vi.fn(() => 'blob:x')
    window.URL.revokeObjectURL = vi.fn()
    rawRequest.mockResolvedValue({ blob: async () => new Blob(['x']) })
  })

  it('fills the pane for a text file', async () => {
    const f = await load(entry('a', 'text/plain', 2))
    await f.previewFile('a')
    expect(f.preview.value?.data.preview_content).toBe('hi')
    expect(f.preview.value?.truncated).toBe(false)
    expect(window.open).not.toHaveBeenCalled()
  })

  it('does not call the preview route for a non-text type', async () => {
    const f = await load(entry('a', 'application/pdf'))
    await f.previewFile('a')
    expect(get.mock.calls.some(([u]) => String(u).includes('/preview/'))).toBe(false)
    expect(window.open).toHaveBeenCalledTimes(1)
    expect(f.preview.value).toBeNull()
  })

  it('falls back to the blob tab when the route says preview_available false', async () => {
    const f = await load(entry('a', 'text/plain'))
    get.mockImplementation(async () => body(null, false))
    await f.previewFile('a')
    expect(f.preview.value).toBeNull()
    expect(window.open).toHaveBeenCalledTimes(1)
    expect(tab.location.href).toBe('blob:x')
  })

  it('falls back to the blob tab, with no error, when the preview request fails', async () => {
    const f = await load(entry('a', 'text/plain'))
    get.mockRejectedValue(new Error('500'))
    await f.previewFile('a')
    expect(f.preview.value).toBeNull()
    expect(f.error.value).toBeNull()
    expect(tab.location.href).toBe('blob:x')
  })

  it('flags truncation when the file is larger than the content shown', async () => {
    const f = await load(entry('a', 'text/plain', 99_999))
    await f.previewFile('a')
    expect(f.preview.value?.truncated).toBe(true)
  })

  it('reports loading while in flight and the latest request wins', async () => {
    const f = await load(entry('a', 'text/plain'), entry('b', 'text/plain'))
    const resolvers: Record<string, (v: unknown) => void> = {}
    get.mockImplementation((url: string) => new Promise((r) => { resolvers[url.split('/').pop()!] = r }))
    const first = f.previewFile('a')
    const second = f.previewFile('b')
    expect(f.previewLoading.value).toBe(true)
    resolvers.b(body('second'))
    await second
    resolvers.a(body('first'))
    await first
    expect(f.preview.value?.filename).toBe('b.dat')
    expect(f.preview.value?.data.preview_content).toBe('second')
    expect(f.previewLoading.value).toBe(false)
  })

  it('closePreview discards a response still in flight', async () => {
    const f = await load(entry('a', 'text/plain'))
    let resolve: (v: unknown) => void = () => {}
    get.mockImplementation(() => new Promise((r) => { resolve = r }))
    const pending = f.previewFile('a')
    f.closePreview()
    resolve(body('late'))
    await pending
    expect(f.preview.value).toBeNull()
    expect(f.previewLoading.value).toBe(false)
  })

  it('clears the pane when its file is deleted or renamed', async () => {
    const f = await load(entry('a', 'text/plain'), entry('b', 'text/plain'))
    del.mockResolvedValue({})
    put.mockResolvedValue({ success: true })
    await f.previewFile('a')
    await f.deleteFile('a')
    expect(f.preview.value).toBeNull()
    await f.previewFile('b')
    await f.renameFile('b', 'c.txt')
    expect(f.preview.value).toBeNull()
  })

  it('keeps the pane when a different file is deleted', async () => {
    const f = await load(entry('a', 'text/plain'), entry('b', 'text/plain'))
    del.mockResolvedValue({})
    await f.previewFile('a')
    await f.deleteFile('b')
    expect(f.preview.value?.fileId).toBe('a')
  })
})
