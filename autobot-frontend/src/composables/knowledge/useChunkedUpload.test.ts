// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/** #19713: chunks go up in order, and after any failure the server's offset says where to carry on. */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { resumeKey, useChunkedUpload } from './useChunkedUpload'

const get = vi.fn()
const post = vi.fn()
const rawRequest = vi.fn()
vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: (...args: unknown[]) => get(...args),
    post: (...args: unknown[]) => post(...args),
    rawRequest: (...args: unknown[]) => rawRequest(...args),
  },
}))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api' }))
vi.mock('@/utils/debugUtils', () => ({ createLogger: () => ({ warn: vi.fn() }) }))

const CHUNK = 4
const file = new File(['0123456789'], 'talk.mp4', { lastModified: 1 })
const created = { upload_id: 'u1', received: 0, total_size: 10, state: 'receiving', chunk_bytes: CHUNK }
const done = { ...created, received: 10, state: 'done', result: { document_id: 'd' } }
const ok = (received: number) => ({ ok: true, status: 200, json: async () => ({ received }) })
const offsets = () => rawRequest.mock.calls.map(([url]) => Number(String(url).split('offset=')[1]))

describe('limits', () => {
  it('reads media types and sizes from the backend, and mirrors nothing', async () => {
    get.mockResolvedValueOnce({ document_max_bytes: 10, media_max_bytes: 99, media_extensions: ['.mp4'] })
    const upload = useChunkedUpload('.pdf')
    expect(upload.maxBytesFor('a.mp4')).toBeNull()
    await upload.loadLimits()
    expect(upload.isMedia('A.MP4')).toBe(true)
    expect(upload.maxBytesFor('a.mp4')).toBe(99)
    expect(upload.maxBytesFor('a.pdf')).toBe(10)
    expect(upload.uploadAccept.value).toBe('.pdf,.mp4')
  })
})

describe('uploadInChunks', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
    post.mockImplementation(async (url: string) => (url.endsWith('/complete') ? {} : created))
    get.mockResolvedValue(done)
  })

  it('sends each chunk in order as raw bytes, then hands the file over', async () => {
    rawRequest.mockResolvedValueOnce(ok(4)).mockResolvedValueOnce(ok(8)).mockResolvedValueOnce(ok(10))
    const seen: number[] = []
    const result = await useChunkedUpload().uploadInChunks(file, { target: 'transcript' }, (p) => seen.push(p))
    expect(offsets()).toEqual([0, 4, 8])
    expect(rawRequest.mock.calls[0][1].body.size).toBe(CHUNK)
    expect(seen).toEqual([40, 80, 100])
    expect(result.result.document_id).toBe('d')
    expect(post).toHaveBeenCalledWith('/api/knowledge_base/uploads/u1/complete', {})
  })

  it('carries on from where the server says after the server lost a chunk', async () => {
    rawRequest
      .mockResolvedValueOnce(ok(4))
      .mockResolvedValueOnce({ ok: false, status: 409, json: async () => ({}) })
      .mockResolvedValueOnce(ok(8))
      .mockResolvedValueOnce(ok(10))
    get.mockResolvedValueOnce({ ...created, received: 4 })
    await useChunkedUpload().uploadInChunks(file, { target: 'transcript' })
    expect(offsets()).toEqual([0, 4, 4, 8])
  })

  it('resumes a session this tab remembers rather than starting another', async () => {
    sessionStorage.setItem(resumeKey(file), 'u1')
    get.mockResolvedValueOnce({ ...created, received: 8 })
    rawRequest.mockResolvedValueOnce(ok(10))
    await useChunkedUpload().uploadInChunks(file, { target: 'transcript' })
    expect(offsets()).toEqual([8])
    expect(post).not.toHaveBeenCalledWith('/api/knowledge_base/uploads', expect.anything())
    expect(sessionStorage.getItem(resumeKey(file))).toBeNull()
  })

  it('starts again when the remembered session is gone', async () => {
    sessionStorage.setItem(resumeKey(file), 'gone')
    get.mockRejectedValueOnce(new Error('404'))
    rawRequest.mockResolvedValueOnce(ok(4)).mockResolvedValueOnce(ok(8)).mockResolvedValueOnce(ok(10))
    await useChunkedUpload().uploadInChunks(file, { target: 'transcript' })
    expect(offsets()).toEqual([0, 4, 8])
  })

  it('reports a refusal rather than retrying it for ever', async () => {
    rawRequest.mockResolvedValueOnce({ ok: false, status: 422, json: async () => ({ detail: 'expired' }) })
    await expect(useChunkedUpload().uploadInChunks(file, { target: 'transcript' })).rejects.toThrow('expired')
  })

  it('reports a failed handoff with its reason', async () => {
    rawRequest.mockResolvedValueOnce(ok(4)).mockResolvedValueOnce(ok(8)).mockResolvedValueOnce(ok(10))
    get.mockResolvedValueOnce({ ...done, state: 'failed', error: 'no audio track' })
    await expect(useChunkedUpload().uploadInChunks(file, { target: 'transcript' })).rejects.toThrow('no audio track')
  })
})
