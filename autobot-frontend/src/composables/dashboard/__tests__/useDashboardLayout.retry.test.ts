// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * A failed load is retried with backoff on a network error or 5xx (#21462); a 4xx is final.
 * `loaded` stays false while retrying, so save and reset write nothing between attempts.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { effectScope } from 'vue'
import { AbsoluteEndpointError, HttpError, RequestTimeoutError } from '@autobot/ui'
import type { DashboardLayout } from '../dashboardLayoutModel'

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), delete: vi.fn() }))
vi.mock('@/utils/ApiClient', () => ({ default: api }))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api' }))
vi.mock('@/utils/debugUtils', () => ({ createLogger: () => ({ error: vi.fn(), warn: vi.fn() }) }))

const { useDashboardLayout } = await import('../useDashboardLayout')

const DEFAULTS = (): DashboardLayout => ({
  dashboards: [{ id: 'default', name: 'n', widgets: [], createdAt: 0, updatedAt: 0 }],
  activeId: 'default',
})
const STORED: DashboardLayout = {
  dashboards: [{ id: 'mine', name: 'Mine', widgets: [], createdAt: 1, updatedAt: 1 }],
  activeId: 'mine',
}
const OPTS = { retries: 2, baseMs: 1000, maxMs: 4000 }
const STORED_BODY = { data: { layout: STORED } }

describe('useDashboardLayout load retry', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    api.get.mockReset()
    api.put.mockReset()
    api.delete.mockReset()
    localStorage.clear()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('a network error then success loads the layout and enables saving, with no error', async () => {
    api.get.mockRejectedValueOnce(new TypeError('Failed to fetch')).mockResolvedValueOnce(STORED_BODY)
    const d = useDashboardLayout('home', DEFAULTS, OPTS)
    const done = d.load()
    await vi.advanceTimersByTimeAsync(0)
    expect(d.loaded.value).toBe(false)
    expect(d.loadError.value).toBeNull()
    expect(await d.save(STORED)).toBe(false) // protected between attempts
    expect(api.put).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1000)
    await done
    expect(api.get).toHaveBeenCalledTimes(2)
    expect(d.loaded.value).toBe(true)
    expect(d.loadError.value).toBeNull()
    expect(d.layout.value.activeId).toBe('mine')
  })

  it('a 5xx then success loads the layout', async () => {
    api.get.mockRejectedValueOnce(new HttpError(503, 'Service Unavailable')).mockResolvedValueOnce(STORED_BODY)
    const d = useDashboardLayout('home', DEFAULTS, OPTS)
    const done = d.load()
    await vi.advanceTimersByTimeAsync(1000)
    await done
    expect(d.loaded.value).toBe(true)
    expect(d.loadError.value).toBeNull()
  })

  it('exhausted retries set loadError and keep the protection on', async () => {
    api.get.mockRejectedValue(new HttpError(502, 'Bad Gateway'))
    const d = useDashboardLayout('home', DEFAULTS, OPTS)
    const done = d.load()
    await vi.advanceTimersByTimeAsync(1000 + 2000)
    await done
    expect(api.get).toHaveBeenCalledTimes(3) // first attempt + 2 retries
    expect(d.loadError.value).toContain('502')
    expect(d.loaded.value).toBe(false)
    expect(await d.save(DEFAULTS())).toBe(false)
    expect(await d.reset()).toBe(false)
    expect(api.put).not.toHaveBeenCalled()
    expect(api.delete).not.toHaveBeenCalled()
  })

  it('a 4xx is not retried and leaves editing off', async () => {
    api.get.mockRejectedValue(new HttpError(403, 'Forbidden'))
    const d = useDashboardLayout('home', DEFAULTS, OPTS)
    await d.load()
    expect(api.get).toHaveBeenCalledTimes(1)
    expect(d.loadError.value).toContain('403')
    expect(d.loaded.value).toBe(false)
  })

  it('"no saved layout yet" (empty data) is a successful load of the defaults', async () => {
    api.get.mockResolvedValueOnce({ data: null })
    const d = useDashboardLayout('home', DEFAULTS, OPTS)
    await d.load()
    expect(api.get).toHaveBeenCalledTimes(1)
    expect(d.loaded.value).toBe(true)
    expect(d.loadError.value).toBeNull()
    expect(d.layout.value.activeId).toBe('default')
  })

  it('load() after exhaustion succeeds and re-enables saving without a reload', async () => {
    api.get.mockRejectedValueOnce(new HttpError(500, 'x')).mockResolvedValueOnce(STORED_BODY)
    const d = useDashboardLayout('home', DEFAULTS, { ...OPTS, retries: 0 })
    await d.load()
    expect(d.loadError.value).not.toBeNull()
    await d.load()
    expect(d.loadError.value).toBeNull()
    expect(d.loaded.value).toBe(true)
    api.put.mockResolvedValueOnce({})
    expect(await d.save(STORED)).toBe(true)
  })

  it('disposing the scope during a retry wait sends no further request', async () => {
    api.get.mockRejectedValue(new HttpError(503, 'x'))
    const scope = effectScope()
    const d = scope.run(() => useDashboardLayout('home', DEFAULTS, OPTS))!
    const done = d.load()
    await vi.advanceTimersByTimeAsync(0)
    scope.stop()
    await vi.advanceTimersByTimeAsync(60000)
    await done
    expect(api.get).toHaveBeenCalledTimes(1)
    expect(d.loadError.value).toBeNull()
    expect(d.loaded.value).toBe(false)
  })

  it('two load() calls while retrying run one loop', async () => {
    api.get.mockRejectedValueOnce(new HttpError(503, 'x')).mockResolvedValueOnce(STORED_BODY)
    const d = useDashboardLayout('home', DEFAULTS, OPTS)
    const first = d.load()
    const second = d.load()
    await vi.advanceTimersByTimeAsync(1000)
    await Promise.all([first, second])
    expect(api.get).toHaveBeenCalledTimes(2)
    expect(d.loaded.value).toBe(true)
  })

  it('retrying is false before, true during the wait, false after success', async () => {
    api.get.mockRejectedValueOnce(new HttpError(503, 'x')).mockResolvedValueOnce(STORED_BODY)
    const d = useDashboardLayout('home', DEFAULTS, OPTS)
    expect(d.retrying.value).toBe(false)
    const done = d.load()
    await vi.advanceTimersByTimeAsync(0)
    expect(d.retrying.value).toBe(true)
    await vi.advanceTimersByTimeAsync(1000)
    await done
    expect(d.retrying.value).toBe(false)
  })

  it('retrying is false again once the retries are exhausted', async () => {
    api.get.mockRejectedValue(new HttpError(503, 'x'))
    const d = useDashboardLayout('home', DEFAULTS, OPTS)
    const done = d.load()
    await vi.advanceTimersByTimeAsync(0)
    expect(d.retrying.value).toBe(true)
    await vi.advanceTimersByTimeAsync(3000)
    await done
    expect(d.retrying.value).toBe(false)
    expect(d.loadError.value).not.toBeNull()
  })

  it('the time budget stops the loop: no attempt starts once the next wait would exceed it', async () => {
    api.get.mockRejectedValue(new HttpError(503, 'x'))
    // waits would be 1000, 2000, 4000...; a 2500 ms budget allows the 1000 wait, not the following 2000
    const d = useDashboardLayout('home', DEFAULTS, { ...OPTS, retries: 10, budgetMs: 2500 })
    const done = d.load()
    await vi.advanceTimersByTimeAsync(1000)
    await done
    expect(api.get).toHaveBeenCalledTimes(2)
    expect(d.loadError.value).not.toBeNull()
    expect(d.retrying.value).toBe(false)
  })

  it('an endpoint refusal is final: one GET, no retry', async () => {
    api.get.mockRejectedValue(new AbsoluteEndpointError('https://evil.example/x'))
    const d = useDashboardLayout('home', DEFAULTS, OPTS)
    await d.load()
    expect(api.get).toHaveBeenCalledTimes(1)
    expect(d.loadError.value).not.toBeNull()
    expect(d.retrying.value).toBe(false)
  })

  it.each([
    ['a fetch network failure', () => new TypeError('Failed to fetch')],
    ['the client timeout, built as the client builds it', () => new RequestTimeoutError(30000)],
    ['a 5xx', () => new HttpError(504, 'Gateway Timeout')],
  ])('retries %s', async (_kind, makeError) => {
    api.get.mockRejectedValueOnce(makeError()).mockResolvedValueOnce(STORED_BODY)
    const d = useDashboardLayout('home', DEFAULTS, OPTS)
    const done = d.load()
    await vi.advanceTimersByTimeAsync(1000)
    await done
    expect(api.get).toHaveBeenCalledTimes(2)
    expect(d.loaded.value).toBe(true)
  })

  it.each([
    ['a body that is not JSON (SyntaxError)', () => new SyntaxError('Unexpected token < in JSON')],
    ['an unknown error', () => new Error('boom')],
    ['a plain Error with the timeout text (the class, not the text, decides)', () => new Error('Request timeout after 30000ms')],
    ['an error merely named like a circuit refusal', () => Object.assign(new Error('open'), { name: 'CircuitBreakerError' })],
  ])('does not retry %s', async (_kind, makeError) => {
    api.get.mockRejectedValue(makeError())
    const d = useDashboardLayout('home', DEFAULTS, OPTS)
    await d.load()
    expect(api.get).toHaveBeenCalledTimes(1)
    expect(d.loadError.value).not.toBeNull()
    expect(d.retrying.value).toBe(false)
    expect(d.loaded.value).toBe(false)
  })

  it('a wait that ends after the deadline starts no new attempt', async () => {
    api.get.mockRejectedValue(new HttpError(503, 'x'))
    const d = useDashboardLayout('home', DEFAULTS, { ...OPTS, retries: 10, budgetMs: 2500 })
    const done = d.load()
    await vi.advanceTimersByTimeAsync(0) // first failure: the 1000 ms wait fits the budget, so it is scheduled
    expect(d.retrying.value).toBe(true)
    vi.setSystemTime(Date.now() + 10000) // the tab was throttled: the clock jumps past the deadline mid-wait
    await vi.advanceTimersByTimeAsync(1000)
    await done
    expect(api.get).toHaveBeenCalledTimes(1)
    expect(d.loadError.value).not.toBeNull()
    expect(d.retrying.value).toBe(false)
  })
})
