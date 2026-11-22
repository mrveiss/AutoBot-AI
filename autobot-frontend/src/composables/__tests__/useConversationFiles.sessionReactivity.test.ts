// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #21159: the conversation id is resolved per request. The file panel stays mounted while the user switches
 * conversations, so a session id captured once made every request hit the previous conversation.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

const get = vi.fn()
const post = vi.fn()
const del = vi.fn()
const rawRequest = vi.fn()
vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get, post, delete: del, rawRequest }) }))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api' }))

import { useConversationFiles } from '../useConversationFiles'

const listed = {
  files: [{ file_id: 'f1', filename: 'a.pdf', original_filename: 'a.pdf', size: 3, mime_type: 'application/pdf', uploaded_at: '2026-10-31T10:00:00Z', uploaded_by: 'alice' }],
  total_files: 1,
  total_size: 3,
}
const base = (id: string) => `/api/conversation-files/conversation/${id}`

describe('useConversationFiles session reactivity (#21159)', () => {
  beforeEach(() => {
    for (const m of [get, post, del, rawRequest]) m.mockReset()
    get.mockResolvedValue(listed)
    post.mockResolvedValue({ success: true })
    del.mockResolvedValue({ success: true })
    rawRequest.mockResolvedValue({ blob: async () => new Blob(['x']) })
    window.URL.createObjectURL = vi.fn(() => 'blob:x')
    window.URL.revokeObjectURL = vi.fn()
    vi.spyOn(window, 'open').mockReturnValue({ location: { href: '' }, close: vi.fn() } as unknown as Window)
  })

  it('loadFiles, upload, delete and preview follow a ref that changes', async () => {
    const session = ref('s1')
    const files = useConversationFiles(session)
    await files.loadFiles()
    expect(get).toHaveBeenLastCalledWith(`${base('s1')}/list`)

    session.value = 's2'
    await files.loadFiles()
    expect(get).toHaveBeenLastCalledWith(`${base('s2')}/list`)

    await files.uploadFiles([new File(['x'], 'b.txt')])
    expect(post.mock.calls[0][0]).toBe(`${base('s2')}/upload`)

    await files.deleteFile('f1')
    expect(del).toHaveBeenLastCalledWith(`${base('s2')}/files/f1`)

    await files.previewFile('f1')
    expect(rawRequest).toHaveBeenLastCalledWith(`${base('s2')}/download/f1`, { method: 'GET' })
  })

  it('follows a getter, and a plain string still works', async () => {
    let id = 'a'
    const viaGetter = useConversationFiles(() => id)
    id = 'b'
    await viaGetter.loadFiles()
    expect(get).toHaveBeenLastCalledWith(`${base('b')}/list`)

    await useConversationFiles('plain').loadFiles()
    expect(get).toHaveBeenLastCalledWith(`${base('plain')}/list`)
  })

  it('guards re-evaluate: an emptied session refuses, a restored one proceeds', async () => {
    const session = ref('')
    const files = useConversationFiles(session)
    await files.loadFiles()
    expect(get).not.toHaveBeenCalled()
    session.value = 's3'
    await files.loadFiles()
    expect(get).toHaveBeenCalledWith(`${base('s3')}/list`)
  })

  it('drops a list reply that arrives after the user left that conversation', async () => {
    const session = ref('s1')
    const files = useConversationFiles(session)
    let release: (v: unknown) => void = () => {}
    get.mockReturnValueOnce(new Promise((r) => { release = r }))
    const pending = files.loadFiles()
    session.value = 's2'
    release(listed)
    await pending
    expect(files.files.value).toEqual([])
  })
})
