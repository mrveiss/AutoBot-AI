// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #20195: the preview opens through the authenticated client. The conversation-file routes read the bearer
 * token from the Authorization header only (no cookie), so `window.open(<route url>)` sent none and was a 401.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const rawRequest = vi.fn()
const get = vi.fn()
vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ rawRequest, get }) }))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api' }))

import { PREVIEW_BLOB_REVOKE_MS, previewBlobType, useConversationFiles } from '../useConversationFiles'

const listed = (mime: string) => ({
  files: [{ file_id: 'f1', filename: 'a.bin', original_filename: 'a.bin', size: 3, mime_type: mime, uploaded_at: '2026-10-31T10:00:00Z', uploaded_by: 'alice' }],
  total_files: 1,
  total_size: 3,
})

describe('useConversationFiles preview (#20195)', () => {
  let tab: { location: { href: string }; close: ReturnType<typeof vi.fn> }
  let blobTypes: string[]

  beforeEach(() => {
    vi.useFakeTimers()
    tab = { location: { href: '' }, close: vi.fn() }
    blobTypes = []
    vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window)
    window.URL.createObjectURL = vi.fn((b: Blob) => {
      blobTypes.push(b.type)
      return 'blob:preview-1'
    })
    window.URL.revokeObjectURL = vi.fn()
    rawRequest.mockReset()
    rawRequest.mockResolvedValue({ blob: async () => new Blob(['x']) })
    get.mockReset()
  })

  afterEach(() => vi.useRealTimers())

  const load = async (mime: string) => {
    get.mockResolvedValue(listed(mime))
    const files = useConversationFiles('s1')
    await files.loadFiles()
    return files
  }

  it('fetches the bytes with the client and opens a blob URL, never the bare route URL', async () => {
    const files = await load('application/pdf')
    await files.previewFile('f1')
    expect(rawRequest).toHaveBeenCalledWith('/api/conversation-files/conversation/s1/download/f1', { method: 'GET' })
    expect(window.open).toHaveBeenCalledTimes(1)
    expect(window.open).toHaveBeenCalledWith('', '_blank') // opened at once, before the await
    expect(tab.location.href).toBe('blob:preview-1')
    expect(blobTypes).toEqual(['application/pdf'])
  })

  it('revokes the blob URL afterwards', async () => {
    const files = await load('image/png')
    await files.previewFile('f1')
    expect(window.URL.revokeObjectURL).not.toHaveBeenCalled()
    vi.advanceTimersByTime(PREVIEW_BLOB_REVOKE_MS)
    expect(window.URL.revokeObjectURL).toHaveBeenCalledWith('blob:preview-1')
  })

  it('opens HTML as plain text so an upload cannot run script in the app origin', async () => {
    const files = await load('text/html')
    await files.previewFile('f1')
    expect(blobTypes).toEqual(['text/plain'])
    expect(previewBlobType('image/svg+xml')).toBeNull()
  })

  it('closes the tab and reports the failure when the fetch fails', async () => {
    rawRequest.mockRejectedValue(new Error('401'))
    const files = await load('application/pdf')
    await files.previewFile('f1')
    expect(tab.close).toHaveBeenCalled()
    expect(files.error.value).toBeTruthy()
  })
})
