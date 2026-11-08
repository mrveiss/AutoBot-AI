// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #21159: the latest request owns the list, the loading flags, the preview pane and the upload progress.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, nextTick } from 'vue'

const get = vi.fn()
const post = vi.fn()
const rawRequest = vi.fn()
vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get, post, rawRequest }) }))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api' }))

import { useConversationFiles } from '../useConversationFiles'

const entry = (id: string, mime = 'text/plain') => ({
  file_id: id, filename: `${id}.dat`, original_filename: `${id}.dat`, size: 5, mime_type: mime,
  uploaded_at: '2026-10-31T10:00:00Z', uploaded_by: 'alice',
})
const listing = (...ids: string[]) => ({ files: ids.map((i) => entry(i)), total_files: ids.length, total_size: 5 })
const deferred = <T>() => {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

describe('useConversationFiles latest-request ownership (#21159)', () => {
  beforeEach(() => {
    for (const m of [get, post, rawRequest]) m.mockReset()
    vi.spyOn(window, 'open').mockReturnValue({ location: { href: '' }, close: vi.fn() } as unknown as Window)
    window.URL.createObjectURL = vi.fn(() => 'blob:x')
    window.URL.revokeObjectURL = vi.fn()
    rawRequest.mockResolvedValue({ blob: async () => new Blob(['x']) })
  })

  it('text then image before the reply leaves no loading pane', async () => {
    get.mockResolvedValueOnce({ files: [entry('t'), entry('i', 'image/png')], total_files: 2, total_size: 10 })
    const f = useConversationFiles('s1')
    await f.loadFiles()
    const reply = deferred<unknown>()
    get.mockReturnValueOnce(reply.promise)
    const text = f.previewFile('t')
    expect(f.previewLoading.value).toBe(true)
    await f.previewFile('i')
    expect(f.previewLoading.value).toBe(false)
    reply.resolve({ preview_available: true, preview_content: 'late', preview_type: 'text' })
    await text
    expect(f.previewLoading.value).toBe(false)
    expect(f.preview.value).toBeNull()
  })

  it('A -> B -> A: only the latest list reply lands, the older A reply is dropped', async () => {
    const session = ref('A')
    const f = useConversationFiles(session)
    const first = deferred<unknown>(); const second = deferred<unknown>(); const third = deferred<unknown>()
    get.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise).mockReturnValueOnce(third.promise)
    const p1 = f.loadFiles()
    session.value = 'B'
    const p2 = f.loadFiles()
    session.value = 'A'
    const p3 = f.loadFiles()
    third.resolve(listing('new'))
    await p3
    expect(f.loading.value).toBe(false)
    first.resolve(listing('old'))
    second.resolve(listing('b'))
    await Promise.all([p1, p2])
    expect(f.files.value.map((x) => x.file_id)).toEqual(['new'])
  })

  it('a stale error does not land in the new conversation and loading tracks the latest request', async () => {
    const session = ref('A')
    const f = useConversationFiles(session)
    const stale = deferred<unknown>(); const fresh = deferred<unknown>()
    get.mockReturnValueOnce(stale.promise).mockReturnValueOnce(fresh.promise)
    const p1 = f.loadFiles()
    session.value = 'B'
    const p2 = f.loadFiles()
    stale.reject(new Error('boom'))
    await p1
    expect(f.error.value).toBeNull()
    expect(f.loading.value).toBe(true)
    fresh.resolve(listing('b'))
    await p2
    expect(f.loading.value).toBe(false)
    expect(f.files.value.map((x) => x.file_id)).toEqual(['b'])
  })

  it('resetForSession clears files, stats, selection and the preview at once', async () => {
    get.mockResolvedValueOnce(listing('a'))
    const f = useConversationFiles('s1')
    await f.loadFiles()
    f.toggleFileSelection('a')
    f.resetForSession()
    expect(f.files.value).toEqual([])
    expect(f.stats.value.total_files).toBe(0)
    expect(f.selectedCount.value).toBe(0)
    expect(f.preview.value).toBeNull()
  })

  describe('upload scoped to the session that started it', () => {
    const upload = async (session: ReturnType<typeof ref<string>>) => {
      const reply = deferred<{ success: boolean }>()
      let onProgress: (e: { loaded: number; total: number }) => void = () => {}
      post.mockImplementationOnce((_u: string, _b: unknown, opts: { onUploadProgress: typeof onProgress }) => {
        onProgress = opts.onUploadProgress
        return reply.promise
      })
      const f = useConversationFiles(session as ReturnType<typeof ref<string>> & { value: string })
      const done = f.uploadFiles([new File(['x'], 'b.txt')])
      await nextTick()
      return { f, done, reply, progress: (n: number) => onProgress({ loaded: n, total: 100 }) }
    }

    it('progress shows for the current session and is ignored after a switch', async () => {
      const session = ref('s1')
      const { f, progress } = await upload(session)
      progress(40)
      expect(f.uploadProgress.value).toBe(40)
      session.value = 's2'
      f.resetForSession()
      progress(80)
      expect(f.uploadProgress.value).toBe(0)
    })

    it('does not reload the new session list or write its error from the old upload', async () => {
      vi.useFakeTimers()
      try {
        const session = ref('s1')
        const { f, done, reply } = await upload(session)
        session.value = 's2'
        f.resetForSession()
        get.mockClear()
        reply.resolve({ success: true })
        expect(await done).toBe(true)
        expect(get).not.toHaveBeenCalled()
        expect(f.uploadProgress.value).toBe(0)
        expect(f.error.value).toBeNull()
      } finally {
        vi.useRealTimers()
      }
    })

    it('still reloads and completes for the current session', async () => {
      vi.useFakeTimers()
      try {
        get.mockResolvedValue(listing('n'))
        const session = ref('s1')
        const { f, done, reply } = await upload(session)
        reply.resolve({ success: true })
        expect(await done).toBe(true)
        expect(f.files.value.map((x) => x.file_id)).toEqual(['n'])
        expect(f.uploadProgress.value).toBe(100)
        vi.advanceTimersByTime(2000)
        expect(f.uploadProgress.value).toBe(0)
      } finally {
        vi.useRealTimers()
      }
    })
  })
})
