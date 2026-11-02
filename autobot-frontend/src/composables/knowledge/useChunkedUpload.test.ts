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
const chunkReply = vi.fn()
vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: (...args: unknown[]) => get(...args),
    post: (...args: unknown[]) => post(...args),
    rawRequest: (...args: unknown[]) => rawRequest(...args),
  },
}))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api' }))
vi.mock('@/utils/debugUtils', () => ({ createLogger: () => ({ warn: vi.fn() }) }))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))

const CHUNK = 4
const file = new File(['0123456789'], 'talk.mp4', { lastModified: 1 })
const created = { upload_id: 'u1', received: 0, total_size: 10, state: 'receiving', chunk_bytes: CHUNK }
const done = { ...created, received: 10, state: 'done', result: { document_id: 'd' } }
const ok = (received: number) => ({ ok: true, status: 200, json: async () => ({ received }) })
const offsets = () =>
  rawRequest.mock.calls
    .filter(([url]) => String(url).includes('offset='))
    .map(([url]) => Number(String(url).split('offset=')[1]))

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
    post.mockResolvedValue({})
    rawRequest.mockImplementation(async (_url: string, options: { method: string }) => {
      if (options.method === 'POST') return { ok: true, status: 200, json: async () => created }
      return chunkReply()
    })
    get.mockResolvedValue(done)
  })

  it('sends each chunk in order as raw bytes, then hands the file over', async () => {
    chunkReply.mockResolvedValueOnce(ok(4)).mockResolvedValueOnce(ok(8)).mockResolvedValueOnce(ok(10))
    const seen: number[] = []
    const result = await useChunkedUpload().uploadInChunks(file, { target: 'transcript' }, (p) => seen.push(p))
    expect(offsets()).toEqual([0, 4, 8])
    const firstChunk = rawRequest.mock.calls.find(([url]) => String(url).includes('offset='))
    expect(firstChunk?.[1].body.size).toBe(CHUNK)
    expect(firstChunk?.[1].timeout).toBeGreaterThan(0)
    expect(seen).toEqual([40, 80, 100])
    expect(result.result.document_id).toBe('d')
    expect(post).toHaveBeenCalledWith('/api/knowledge_base/uploads/u1/complete', {})
  })

  it('carries on from where the server says after the server lost a chunk', async () => {
    chunkReply
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
    chunkReply.mockResolvedValueOnce(ok(10))
    await useChunkedUpload().uploadInChunks(file, { target: 'transcript' })
    expect(offsets()).toEqual([8])
    expect(rawRequest.mock.calls.some(([, options]) => options.method === 'POST')).toBe(false)
    expect(sessionStorage.getItem(resumeKey(file))).toBeNull()
  })

  it('starts again when the remembered session is gone', async () => {
    sessionStorage.setItem(resumeKey(file), 'gone')
    get.mockRejectedValueOnce(new Error('404'))
    chunkReply.mockResolvedValueOnce(ok(4)).mockResolvedValueOnce(ok(8)).mockResolvedValueOnce(ok(10))
    await useChunkedUpload().uploadInChunks(file, { target: 'transcript' })
    expect(offsets()).toEqual([0, 4, 8])
  })

  it('reports a refusal rather than retrying it for ever', async () => {
    chunkReply.mockResolvedValueOnce({ ok: false, status: 422, json: async () => ({ detail: { code: 'upload.refused' } }) })
    await expect(useChunkedUpload().uploadInChunks(file, { target: 'transcript' })).rejects.toThrow('knowledge.upload.chunked.failed')
  })

  it('reports a failed handoff with its reason', async () => {
    chunkReply.mockResolvedValueOnce(ok(4)).mockResolvedValueOnce(ok(8)).mockResolvedValueOnce(ok(10))
    get.mockResolvedValueOnce({ ...done, state: 'failed', error: 'upload.checksum_mismatch' })
    await expect(useChunkedUpload().uploadInChunks(file, { target: 'transcript' })).rejects.toThrow('knowledge.upload.chunked.checksum')
  })

  it('words a full disk rather than retrying it', async () => {
    rawRequest.mockReset()
    rawRequest.mockResolvedValueOnce({ ok: false, status: 507, json: async () => ({ detail: { code: 'upload.no_space' } }) })
    await expect(useChunkedUpload().uploadInChunks(file, { target: 'transcript' })).rejects.toThrow('knowledge.upload.chunked.noSpace')
  })

  it('cancelling frees what was staged and forgets the session', async () => {
    sessionStorage.setItem(resumeKey(file), 'u1')
    rawRequest.mockReset()
    rawRequest.mockResolvedValue({ ok: true, status: 200 })
    await useChunkedUpload().cancelUpload(file)
    expect(rawRequest).toHaveBeenCalledWith('/api/knowledge_base/uploads/u1', { method: 'DELETE' })
    expect(sessionStorage.getItem(resumeKey(file))).toBeNull()
  })
})
