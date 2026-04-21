// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * useFetchEndpoint tests (#5276)
 *
 * Focused on the new `parseResponse` hook — verifies non-JSON payloads
 * (text/markdown) route through the same loading/error/assign pipeline
 * as JSON fetchers.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useFetchEndpoint } from '../useFetchEndpoint'

vi.mock('@/utils/fetchWithAuth', () => ({
  fetchWithAuth: vi.fn(),
}))

vi.mock('@/config/AppConfig.js', () => ({
  default: {
    getServiceUrl: vi.fn(async () => 'http://backend'),
  },
}))

import { fetchWithAuth } from '@/utils/fetchWithAuth'
const mockFetch = fetchWithAuth as unknown as ReturnType<typeof vi.fn>

const mkResponse = (body: string, opts: { ok?: boolean; status?: number } = {}) => ({
  ok: opts.ok ?? true,
  status: opts.status ?? 200,
  json: async () => JSON.parse(body),
  text: async () => body,
})

describe('useFetchEndpoint parseResponse hook (#5276)', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  it('defaults to JSON parsing when parseResponse is omitted', async () => {
    mockFetch.mockResolvedValue(mkResponse('{"value": 42}'))
    const ep = useFetchEndpoint<{ value: number }, number>({
      path: '/api/x',
      pickData: (r) => r.value,
    })
    await ep.load()
    expect(ep.data.value).toBe(42)
    expect(ep.error.value).toBe('')
  })

  it('uses parseResponse when provided — text/markdown case', async () => {
    const markdownBody = '# Header\n\nSome **markdown** content'
    mockFetch.mockResolvedValue(mkResponse(markdownBody))
    const ep = useFetchEndpoint<string, string>({
      path: '/api/report',
      parseResponse: async (r) => await r.text(),
      pickData: (raw) => raw,
    })
    await ep.load()
    expect(ep.data.value).toBe(markdownBody)
    expect(ep.error.value).toBe('')
  })

  it('parseResponse result is passed to pickData', async () => {
    mockFetch.mockResolvedValue(mkResponse('raw text'))
    const pickData = vi.fn((raw: string) => raw.toUpperCase())
    const ep = useFetchEndpoint<string, string>({
      path: '/api/x',
      parseResponse: async (r) => await r.text(),
      pickData,
    })
    await ep.load()
    expect(pickData).toHaveBeenCalledWith('raw text')
    expect(ep.data.value).toBe('RAW TEXT')
  })

  it('parseResponse throw propagates through the normal error path', async () => {
    mockFetch.mockResolvedValue(mkResponse('ok'))
    const ep = useFetchEndpoint<string, string>({
      path: '/api/x',
      parseResponse: async () => {
        throw new Error('parse kaboom')
      },
      pickData: (raw) => raw,
    })
    await ep.load()
    expect(ep.error.value).toBe('parse kaboom')
    expect(ep.data.value).toBe(null)
  })

  it('parseResponse is not invoked when response is not ok', async () => {
    mockFetch.mockResolvedValue(mkResponse('err', { ok: false, status: 500 }))
    const parser = vi.fn()
    const ep = useFetchEndpoint<string, string>({
      path: '/api/x',
      parseResponse: parser,
      pickData: (raw) => raw,
    })
    await ep.load()
    expect(parser).not.toHaveBeenCalled()
    expect(ep.error.value).toContain('500')
  })
})
