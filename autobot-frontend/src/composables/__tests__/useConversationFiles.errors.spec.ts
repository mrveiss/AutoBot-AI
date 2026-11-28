// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #21159: every error.value the composable sets is translated; a server detail still wins over the fallback.
import { describe, it, expect, vi } from 'vitest'

const { put, get, del, rawRequest } = vi.hoisted(() => ({ put: vi.fn(), get: vi.fn(), del: vi.fn(), rawRequest: vi.fn() }))

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ put, get, delete: del, rawRequest }) }))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api' }))
vi.mock('@/i18n', () => ({
  default: { global: { t: (key: string) => `t:${key}` } },
}))

import { useConversationFiles } from '@/composables/useConversationFiles'

describe('conversation file errors (#21159)', () => {
  it('rename failure with no server detail shows the translated fallback', async () => {
    put.mockRejectedValueOnce({})
    const files = useConversationFiles('s1')
    expect(await files.renameFile('f1', 'b.txt')).toBe(false)
    expect(files.error.value).toBe('t:chat.conversationFiles.renameFailed')
  })

  it('rename failure keeps the server detail', async () => {
    put.mockRejectedValueOnce({ response: { data: { detail: 'Name already taken' } } })
    const files = useConversationFiles('s1')
    await files.renameFile('f1', 'b.txt')
    expect(files.error.value).toBe('Name already taken')
  })

  it('a rename the server declines (success false) is translated', async () => {
    put.mockResolvedValueOnce({ success: false })
    const files = useConversationFiles('s1')
    await files.renameFile('f1', 'b.txt')
    expect(files.error.value).toBe('t:chat.conversationFiles.renameFailed')
  })

  it('the missing-parameter guard is translated', async () => {
    const files = useConversationFiles('s1')
    expect(await files.renameFile('', 'b.txt')).toBe(false)
    expect(files.error.value).toBe('t:chat.conversationFiles.missingParameters')
  })

  it('the no-session guard is translated', async () => {
    const files = useConversationFiles('')
    await files.loadFiles()
    expect(files.error.value).toBe('t:chat.conversationFiles.noSession')
  })

  const listing = { files: [{ file_id: 'f1', filename: 'a.txt', original_filename: 'a.txt', size: 1, mime_type: 'text/plain', uploaded_at: '2026-11-01T10:00:00Z', uploaded_by: 'u' }], total_files: 1, total_size: 1 }

  it.each([
    ['read', 'readFailed', async (f: ReturnType<typeof useConversationFiles>) => { get.mockRejectedValueOnce({}); await f.getFileContent('f1') }],
    ['delete', 'deleteFailed', async (f: ReturnType<typeof useConversationFiles>) => { del.mockRejectedValueOnce({}); await f.deleteFile('f1') }],
    ['download', 'downloadFailed', async (f: ReturnType<typeof useConversationFiles>) => { rawRequest.mockRejectedValueOnce({}); await f.downloadFile('f1', 'a.txt') }],
    ['preview', 'previewFailed', async (f: ReturnType<typeof useConversationFiles>) => { rawRequest.mockRejectedValueOnce({}); await f.previewFile('f1') }],
  ])('%s failure with no server detail shows the translated fallback', async (_name, key, run) => {
    get.mockResolvedValueOnce(listing)
    const files = useConversationFiles('s1')
    await files.loadFiles()
    get.mockResolvedValue(null) // the preview route has nothing inline, so the bytes path runs
    vi.spyOn(window, 'open').mockReturnValue({ close: vi.fn(), location: { href: '' } } as unknown as Window)
    await run(files)
    expect(files.error.value).toBe(`t:chat.conversationFiles.${key}`)
  })
})
