// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
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

describe('useFetchEndpoint fallbackData hook (#5389)', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  it('on fetch failure, data.value is set to fallbackData and error stays empty', async () => {
    mockFetch.mockResolvedValue(mkResponse('err', { ok: false, status: 500 }))
    const ep = useFetchEndpoint<{ items: string[] }, { items: string[] }>({
      path: '/api/x',
      pickData: (r) => r,
      fallbackData: { items: ['cached'] },
    })
    await ep.load()
    expect(ep.data.value).toEqual({ items: ['cached'] })
    expect(ep.error.value).toBe('')
  })

  it('fallbackData factory is called lazily', async () => {
    mockFetch.mockRejectedValue(new Error('network'))
    const factory = vi.fn(() => ({ items: ['fresh'] }))
    const ep = useFetchEndpoint<{ items: string[] }, { items: string[] }>({
      path: '/api/x',
      pickData: (r) => r,
      fallbackData: factory,
    })
    await ep.load()
    expect(factory).toHaveBeenCalledOnce()
    expect(ep.data.value).toEqual({ items: ['fresh'] })
  })

  it('onError still fires when fallbackData is provided', async () => {
    mockFetch.mockRejectedValue(new Error('boom'))
    const onError = vi.fn()
    const ep = useFetchEndpoint<string, string>({
      path: '/api/x',
      pickData: (r) => r,
      fallbackData: 'stale',
      onError,
    })
    await ep.load()
    // #5457: onError now receives context (undefined when not provided).
    expect(onError).toHaveBeenCalledWith('boom', expect.any(Error), undefined)
    expect(ep.data.value).toBe('stale')
    expect(ep.error.value).toBe('')
  })

  it('without fallbackData, errors behave as before (data=null, error set)', async () => {
    mockFetch.mockRejectedValue(new Error('boom'))
    const ep = useFetchEndpoint<string, string>({
      path: '/api/x',
      pickData: (r) => r,
    })
    await ep.load()
    expect(ep.data.value).toBe(null)
    expect(ep.error.value).toBe('boom')
  })

  it('successful fetch bypasses fallbackData entirely', async () => {
    mockFetch.mockResolvedValue(mkResponse('{"items": ["live"]}'))
    const ep = useFetchEndpoint<{ items: string[] }, { items: string[] }>({
      path: '/api/x',
      pickData: (r) => r,
      fallbackData: { items: ['cached'] },
    })
    await ep.load()
    expect(ep.data.value).toEqual({ items: ['live'] })
  })
})

describe('useFetchEndpoint context hook (#5457)', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  it('onSuccess receives the per-call context', async () => {
    mockFetch.mockResolvedValue(mkResponse('{"value": 42}'))
    const onSuccess = vi.fn()
    const ep = useFetchEndpoint<{ value: number }, number, { quick: boolean }>({
      path: '/api/x',
      pickData: (r) => r.value,
      onSuccess,
    })
    await ep.load(undefined, { quick: true })
    expect(onSuccess).toHaveBeenCalledWith(42, { value: 42 }, { quick: true })
  })

  it('concurrent load() calls each receive their own context in onSuccess', async () => {
    // Simulates the #5455 exportReport race: two concurrent load() calls
    // with different context must each see their own context in onSuccess.
    const successCalls: Array<{ quick: boolean; data: number }> = []
    mockFetch.mockImplementation(async () =>
      mkResponse(JSON.stringify({ value: successCalls.length + 1 })),
    )
    const ep = useFetchEndpoint<{ value: number }, number, { quick: boolean }>({
      path: '/api/x',
      pickData: (r) => r.value,
      onSuccess: (data, _raw, ctx) => {
        successCalls.push({ quick: ctx.quick, data })
      },
    })
    await Promise.all([
      ep.load(undefined, { quick: true }),
      ep.load(undefined, { quick: false }),
    ])
    expect(successCalls).toHaveLength(2)
    const quickCall = successCalls.find((c) => c.quick === true)
    const fullCall = successCalls.find((c) => c.quick === false)
    expect(quickCall).toBeDefined()
    expect(fullCall).toBeDefined()
  })

  it('onError receives the context', async () => {
    mockFetch.mockRejectedValue(new Error('boom'))
    const onError = vi.fn()
    const ep = useFetchEndpoint<string, string, string>({
      path: '/api/x',
      pickData: (r) => r,
      onError,
    })
    await ep.load(undefined, 'request-42')
    expect(onError).toHaveBeenCalledWith('boom', expect.any(Error), 'request-42')
  })

  it('onNoData receives the context', async () => {
    mockFetch.mockResolvedValue(mkResponse('{"value": 42}'))
    const onNoData = vi.fn()
    const ep = useFetchEndpoint<{ value: number }, number, string>({
      path: '/api/x',
      pickData: () => null, // trigger no-data path
      onNoData,
    })
    await ep.load(undefined, 'tag-xyz')
    expect(onNoData).toHaveBeenCalledWith('tag-xyz')
  })

  it('onResponse receives the context for error-shape override', async () => {
    mockFetch.mockResolvedValue(mkResponse('err', { ok: false, status: 504 }))
    const onResponse = vi.fn().mockReturnValue('timeout')
    const ep = useFetchEndpoint<string, string, { traceId: string }>({
      path: '/api/x',
      pickData: (r) => r,
      onResponse,
    })
    await ep.load(undefined, { traceId: 't-9' })
    expect(onResponse).toHaveBeenCalledWith(expect.anything(), { traceId: 't-9' })
    expect(ep.error.value).toBe('timeout')
  })

  it('context is optional — existing callers without Ctx still work', async () => {
    mockFetch.mockResolvedValue(mkResponse('{"value": 42}'))
    const onSuccess = vi.fn()
    const ep = useFetchEndpoint<{ value: number }, number>({
      path: '/api/x',
      pickData: (r) => r.value,
      onSuccess,
    })
    await ep.load() // no context arg
    expect(onSuccess).toHaveBeenCalledWith(42, { value: 42 }, undefined)
  })
})
