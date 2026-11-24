// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Behaviour parity for the composer's attachments, moved out of ChatInput.vue (#18243): an oversize file is
 * refused with a toast, files upload in parallel, a failed upload keeps its row for a retry, and only server
 * ids reach a send (#20195).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const m = vi.hoisted(() => ({ showToast: vi.fn(), post: vi.fn(), ensure: vi.fn() }))

vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string, p?: Record<string, unknown>) => (p ? `${k}:${JSON.stringify(p)}` : k) }) }))
vi.mock('@autobot/ui', () => ({ useToast: () => ({ showToast: m.showToast }) }))
vi.mock('@/stores/useChatStore', () => ({ useChatStore: () => ({}) }))
vi.mock('@/models/controllers', () => ({ useChatController: () => ({}) }))
vi.mock('@/utils/formatHelpers', () => ({ formatFileSize: (n: number) => `${n}B` }))
vi.mock('@/utils/conversationFileUpload', () => ({
  postConversationUpload: m.post,
  ensureUploadSession: m.ensure,
  describeUploadError: (e: Error) => `described:${e.message}`,
  uploadEtaSeconds: () => 3,
  ConversationUploadError: class extends Error {},
}))
vi.mock('@/composables/useUploadCancel', () => ({
  isUploadCancelled: () => false,
  useUploadCancel: () => ({ begin: () => new AbortController().signal, settle: () => false, isCancellable: () => true, cancel: vi.fn() }),
}))

import { MAX_FILE_SIZE, useComposerUploads } from '../useComposerUploads'

const pick = (...files: File[]) => ({ target: { files, value: 'x' } }) as unknown as Event

beforeEach(() => {
  Object.values(m).forEach((f) => f.mockReset())
  m.ensure.mockResolvedValue('session-1')
  vi.useRealTimers()
})

describe('useComposerUploads', () => {
  it('refuses an oversize file with a toast and never lists it', async () => {
    const u = useComposerUploads()
    const big = new File(['x'], 'big.bin')
    Object.defineProperty(big, 'size', { value: MAX_FILE_SIZE + 1 })
    await u.handleFileSelect(pick(big))
    expect(m.showToast).toHaveBeenCalledWith(expect.stringContaining('chat.input.fileTooLarge'), 'warning')
    expect(u.uploadProgress.value).toEqual([])
    expect(u.attachedFiles.value).toEqual([])
    expect(m.post).not.toHaveBeenCalled()
  })

  it('attaches a file once uploaded and maps it to its server id', async () => {
    m.post.mockResolvedValue({ file_info: { file_id: 'srv-1' }, upload_id: 'up-1' })
    const u = useComposerUploads()
    const file = new File(['a'], 'a.txt')
    await u.handleFileSelect(pick(file))
    expect(u.attachedFiles.value).toEqual([file])
    expect(u.serverFileIds([file])).toEqual(['srv-1'])
    expect(u.serverFileIds([new File(['b'], 'b.txt')])).toEqual([]) // an unuploaded file contributes no id
    expect(u.uploadProgress.value[0].phase).toBe('complete')
  })

  it('uploads every file, in parallel, through one session', async () => {
    m.post.mockResolvedValue({ file_info: { file_id: 'f' } })
    const u = useComposerUploads()
    await u.handleFileSelect(pick(new File(['a'], 'a.txt'), new File(['b'], 'b.txt')))
    expect(m.post).toHaveBeenCalledTimes(2)
    expect(u.attachedFiles.value).toHaveLength(2)
  })

  it('keeps a failed upload as an error row, with the described reason, and attaches nothing', async () => {
    m.post.mockRejectedValue(new Error('boom'))
    const u = useComposerUploads()
    await u.handleFileSelect(pick(new File(['a'], 'a.txt')))
    expect(u.attachedFiles.value).toEqual([])
    expect(u.uploadProgress.value[0]).toMatchObject({ phase: 'failed', error: 'described:boom', progress: 0 })
  })

  it('a retry that succeeds attaches the file once', async () => {
    m.post.mockRejectedValueOnce(new Error('boom')).mockResolvedValue({ file_info: { file_id: 'srv-2' } })
    const u = useComposerUploads()
    const file = new File(['a'], 'a.txt')
    await u.handleFileSelect(pick(file))
    await u.retryUpload(u.uploadProgress.value[0].id)
    await u.retryUpload(u.uploadProgress.value[0].id)
    expect(u.attachedFiles.value).toEqual([file])
  })

  it('blocks a send while a selection uploads, and releases it when it settles', async () => {
    let finish!: (v: unknown) => void
    m.post.mockReturnValue(new Promise((resolve) => { finish = resolve }))
    const u = useComposerUploads()
    const selecting = u.handleFileSelect(pick(new File(['a'], 'a.txt')))
    await Promise.resolve()
    expect(u.hasPendingUploads.value).toBe(true)
    finish({ file_info: { file_id: 'f' } })
    await selecting
    expect(u.hasPendingUploads.value).toBe(false)
  })

  it('a retry attaches a different file that shares a name with an attached one', async () => {
    m.post.mockResolvedValueOnce({ file_info: { file_id: 'one' } }).mockRejectedValueOnce(new Error('boom')).mockResolvedValue({ file_info: { file_id: 'two' } })
    const u = useComposerUploads()
    const first = new File(['a'], 'report.txt')
    const second = new File(['b'], 'report.txt')
    await u.handleFileSelect(pick(first))
    await u.handleFileSelect(pick(second))
    await u.retryUpload(u.uploadProgress.value.find((r) => r.phase === 'failed')!.id)
    expect(u.attachedFiles.value).toEqual([first, second])
  })

  it('removes one attached file and clears them all', async () => {
    m.post.mockResolvedValue({ file_info: { file_id: 'f' } })
    const u = useComposerUploads()
    await u.handleFileSelect(pick(new File(['a'], 'a.txt'), new File(['b'], 'b.txt')))
    u.removeFile(0)
    expect(u.attachedFiles.value.map((f) => f.name)).toEqual(['b.txt'])
    u.clearAllFiles()
    expect(u.attachedFiles.value).toEqual([])
  })

  it('clears the file input so the same file can be picked again', async () => {
    m.post.mockResolvedValue({})
    const event = pick(new File(['a'], 'a.txt'))
    await useComposerUploads().handleFileSelect(event)
    expect((event.target as HTMLInputElement).value).toBe('')
  })
})
