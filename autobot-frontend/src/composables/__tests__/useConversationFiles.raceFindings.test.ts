// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #21337: stale-response and session-switch races deferred from the conversation file UI review (#21214).
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

const rawRequest = vi.fn()
const get = vi.fn()
const del = vi.fn()
vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ rawRequest, get, delete: del, put: vi.fn() }) }))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api' }))
vi.mock('@/i18n', () => ({
  default: { global: { t: (key: string, params: Record<string, unknown> = {}) => `${key}|${JSON.stringify(params)}` } },
}))

import { useConversationFiles } from '../useConversationFiles'

const entry = (id: string, mime: string) => ({
  file_id: id, filename: `${id}.dat`, original_filename: `${id}.dat`, size: 5, mime_type: mime,
  uploaded_at: '2026-10-31T10:00:00Z', uploaded_by: 'alice',
})
const listing = (...files: ReturnType<typeof entry>[]) => ({ files, total_files: files.length, total_size: 10 })
const body = (content: string | null, available = true) => ({
  file_info: { file_id: 'x' }, preview_available: available, preview_content: content, preview_type: 'text',
})

describe('preview races (#21337)', () => {
  let tab: { location: { href: string }; close: ReturnType<typeof vi.fn> }
  const load = async (session: string, ...files: ReturnType<typeof entry>[]) => {
    get.mockImplementation(async (url: string) => (url.includes('/list') ? listing(...files) : body('hi')))
    const f = useConversationFiles(session)
    await f.loadFiles()
    return f
  }

  beforeEach(() => {
    get.mockReset(); rawRequest.mockReset(); del.mockReset()
    tab = { location: { href: '' }, close: vi.fn() }
    vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window)
    window.URL.createObjectURL = vi.fn(() => 'blob:x')
    window.URL.revokeObjectURL = vi.fn()
    rawRequest.mockResolvedValue({ blob: async () => new Blob(['x']) })
  })

  it('a cancelled bytes preview closes its tab instead of navigating it', async () => {
    const f = await load('s1', entry('a', 'application/pdf'))
    let release: (v: unknown) => void = () => {}
    rawRequest.mockImplementation(() => new Promise((r) => { release = r }))
    const pending = f.previewFile('a')
    f.closePreview()
    release({ blob: async () => new Blob(['x']) })
    await pending
    expect(tab.location.href).toBe('')
    expect(tab.close).toHaveBeenCalled()
  })

  it('a failed preview request is reported as a preview failure when the bytes fail too', async () => {
    const f = await load('s1', entry('a', 'text/plain'))
    get.mockRejectedValue(new Error('500'))
    rawRequest.mockRejectedValue(new Error('bytes down'))
    await f.previewFile('a')
    expect(f.error.value).toBe('chat.conversationFiles.previewFailed|{}')
  })

  it('a bytes failure after a clean "no inline preview" keeps the bytes error', async () => {
    const f = await load('s1', entry('a', 'text/plain'))
    get.mockImplementation(async () => body(null, false))
    rawRequest.mockRejectedValue(new Error('bytes down'))
    await f.previewFile('a')
    expect(f.error.value).toBe('bytes down')
  })

  it('deleting the file whose preview is still loading revokes the request', async () => {
    const f = await load('s1', entry('a', 'text/plain'))
    let release: (v: unknown) => void = () => {}
    get.mockImplementation(() => new Promise((r) => { release = r }))
    del.mockResolvedValue({})
    const pending = f.previewFile('a')
    await f.deleteFile('a')
    release(body('late'))
    await pending
    expect(f.preview.value).toBeNull()
    expect(f.previewLoading.value).toBe(false)
  })

  it('starting the preview of file B clears file A from the pane while B loads', async () => {
    const f = await load('s1', entry('a', 'text/plain'), entry('b', 'text/plain'))
    await f.previewFile('a')
    expect(f.preview.value?.fileId).toBe('a')
    get.mockImplementation(() => new Promise(() => {}))
    void f.previewFile('b')
    expect(f.preview.value).toBeNull()
  })

  it('an obsolete request does not write its error into the current alert', async () => {
    const f = await load('s1', entry('a', 'application/pdf'))
    let fail: (e: unknown) => void = () => {}
    rawRequest.mockImplementation(() => new Promise((_r, rej) => { fail = rej }))
    const pending = f.previewFile('a')
    f.closePreview()
    fail(new Error('old failure'))
    await pending
    expect(f.error.value).toBeNull()
  })
})

describe('bulk delete (#21337)', () => {
  beforeEach(() => { get.mockReset(); del.mockReset() })

  it('sends every id to the session that asked, even after a switch mid-loop', async () => {
    const session = ref('s1')
    get.mockImplementation(async () => listing(entry('a', 'text/plain'), entry('b', 'text/plain')))
    const f = useConversationFiles(session)
    await f.loadFiles()
    f.toggleFileSelection('a'); f.toggleFileSelection('b')
    del.mockImplementation(async () => { session.value = 's2' })
    await f.deleteSelectedFiles()
    expect(del.mock.calls.map(([u]) => u)).toEqual([
      '/api/conversation-files/conversation/s1/files/a',
      '/api/conversation-files/conversation/s1/files/b',
    ])
  })

  it('surfaces a failure instead of reporting success, and keeps the failed file selected', async () => {
    get.mockImplementation(async () => listing(entry('a', 'text/plain'), entry('b', 'text/plain')))
    const f = useConversationFiles('s1')
    await f.loadFiles()
    f.toggleFileSelection('a'); f.toggleFileSelection('b')
    del.mockRejectedValueOnce({ response: { status: 403, data: { detail: 'not yours' } } }).mockResolvedValueOnce({})
    expect(await f.deleteSelectedFiles()).toBe(false)
    expect(f.error.value).toBe('not yours')
    expect(Array.from(f.selectedFileIds.value)).toEqual(['a'])
  })
})
