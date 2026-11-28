// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #21029: the File Browser saves exactly the bytes the backend serves.
 * The payload is invalid UTF-8, so any text decode on the way changes it.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DOWNLOAD_UNAUTHORIZED_KEY, downloadAdminFile, downloadErrorKey } from '@/composables/adminFileDownload'

const PAYLOAD = new Uint8Array([0xff, 0xd8, 0x00, 0x80, 0x89, 0x50, 0x4e, 0x47])

/** Blob#arrayBuffer is implemented by both the test DOM's Blob and Node's (what Response#blob yields). */
async function bytesOf(blob: Blob): Promise<number[]> {
  return Array.from(new Uint8Array(await blob.arrayBuffer()))
}

describe('downloadAdminFile (#21029)', () => {
  let saved: Blob | null
  let savedName: string | null

  beforeEach(() => {
    saved = null
    savedName = null
    vi.spyOn(URL, 'createObjectURL').mockImplementation((b: Blob | MediaSource) => {
      saved = b as Blob
      return 'blob:test'
    })
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      savedName = this.download
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('control: a text decode of this payload is lossy, so the test can detect one', async () => {
    const decoded = new TextDecoder('utf-8').decode(PAYLOAD)
    const viaText = new Blob([decoded])
    expect(await bytesOf(viaText)).not.toEqual(Array.from(PAYLOAD))
  })

  it('saves the served bytes unchanged under the entry name', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(PAYLOAD, { status: 200, headers: { 'Content-Type': 'application/octet-stream' } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await downloadAdminFile('/home/autobot/a.bin', 'a.bin')

    expect(String(fetchMock.mock.calls[0][0])).toContain('/files/raw?path=%2Fhome%2Fautobot%2Fa.bin')
    expect(saved).not.toBeNull()
    expect(await bytesOf(saved as Blob)).toEqual(Array.from(PAYLOAD))
    expect(savedName).toBe('a.bin')
    // saveBlob revokes the object URL in a later task; let it run while the spy is still installed
    await new Promise<void>((resolve) => setTimeout(resolve, 0))
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:test')
  })

  it('saves nothing and throws on a non-2xx answer', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('nope', { status: 404, statusText: 'Not Found' })))
    await expect(downloadAdminFile('/home/autobot/x', 'x')).rejects.toThrow('404')
    expect(saved).toBeNull()
  })

  it('a 401 saves nothing and maps to the i18n key; other errors do not', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('no', { status: 401, statusText: 'Unauthorized' })))
    const failure = await downloadAdminFile('/home/autobot/x', 'x').catch((e: unknown) => e)
    expect(saved).toBeNull()
    expect(downloadErrorKey(failure)).toBe(DOWNLOAD_UNAUTHORIZED_KEY)
    expect(downloadErrorKey(new Error('boom'))).toBeNull()
  })
})
