// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { RequestTimeoutError } from '@autobot/ui'
import { monitorApiCall } from '@/utils/apiCallMonitor'
import { ApiClient } from '@/utils/ApiClient'

type Rum = { trackApiCall: ReturnType<typeof vi.fn>; reportCriticalIssue: ReturnType<typeof vi.fn> }

function stubRum(): Rum {
  const rum: Rum = {
    trackApiCall: vi.fn().mockReturnValue({ isTimeout: false, duration: 12 }),
    reportCriticalIssue: vi.fn(),
  }
  window.rum = rum as unknown as Window['rum']
  return rum
}

describe('monitorApiCall (#21583)', () => {
  let rum: Rum
  beforeEach(() => {
    rum = stubRum()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    delete (window as { rum?: unknown }).rum
  })

  it('records a resolved call with its numeric status and returns the response untouched', async () => {
    const response = new Response('ok', { status: 201 })
    const result = await monitorApiCall('POST', '/api/x', async () => response)
    expect(result).toBe(response)
    expect(rum.trackApiCall).toHaveBeenCalledWith('POST', '/api/x', expect.any(Number), expect.any(Number), 201, undefined, false)
    expect(rum.reportCriticalIssue).not.toHaveBeenCalled()
  })

  it('records a failed call and rethrows the same error without a critical report', async () => {
    const failure = new Error('boom')
    await expect(monitorApiCall('GET', '/api/x', async () => { throw failure })).rejects.toBe(failure)
    expect(rum.trackApiCall).toHaveBeenCalledWith('GET', '/api/x', expect.any(Number), expect.any(Number), 'error', failure, false)
    expect(rum.reportCriticalIssue).not.toHaveBeenCalled()
  })

  it('passes the typed timeout to trackApiCall, which records and reports it once', async () => {
    const timeout = new RequestTimeoutError(5000)
    await expect(monitorApiCall('GET', '/api/slow', async () => { throw timeout })).rejects.toBe(timeout)
    expect(rum.trackApiCall).toHaveBeenCalledWith('GET', '/api/slow', expect.any(Number), expect.any(Number), 'error', timeout, true)
    expect(rum.reportCriticalIssue).not.toHaveBeenCalled()
  })

  it('passes a fetch aborted by AbortSignal.timeout() as a timeout', async () => {
    const aborted = new DOMException('signal timed out', 'TimeoutError')
    await expect(monitorApiCall('GET', '/api/slow', async () => { throw aborted })).rejects.toBe(aborted)
    expect(rum.trackApiCall).toHaveBeenCalledWith('GET', '/api/slow', expect.any(Number), expect.any(Number), 'error', expect.anything(), true)
  })

  it('does not classify by message text: a plain error that says timeout is not a timeout', async () => {
    await expect(monitorApiCall('GET', '/api/x', async () => { throw new Error('request timeout') })).rejects.toThrow('request timeout')
    expect(rum.trackApiCall).toHaveBeenCalledWith('GET', '/api/x', expect.any(Number), expect.any(Number), 'error', expect.any(Error), false)
  })

  it('does not record an abort from unmount or navigation', async () => {
    const abort = new DOMException('aborted', 'AbortError')
    await expect(monitorApiCall('GET', '/api/x', async () => { throw abort })).rejects.toBe(abort)
    expect(rum.trackApiCall).not.toHaveBeenCalled()
  })

  it('passes the outcome through when RumAgent throws', async () => {
    rum.trackApiCall.mockImplementation(() => { throw new Error('rum down') })
    const response = new Response('ok')
    await expect(monitorApiCall('GET', '/api/x', async () => response)).resolves.toBe(response)
  })

  it('passes the outcome through when RumAgent is not loaded', async () => {
    delete (window as { rum?: unknown }).rum
    const response = new Response('ok')
    await expect(monitorApiCall('GET', '/api/x', async () => response)).resolves.toBe(response)
  })
})

describe('ApiClient.rawRequest is the monitored seam (#21583)', () => {
  let rum: Rum
  beforeEach(() => {
    rum = stubRum()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    delete (window as { rum?: unknown }).rum
  })

  it('times a real client request through RumAgent', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 200 })))
    await new ApiClient().rawRequest('/api/ping', { method: 'PUT' })
    expect(rum.trackApiCall).toHaveBeenCalledWith('PUT', '/api/ping', expect.any(Number), expect.any(Number), 200, undefined, false)
  })

  it('records a failing client request and rethrows it', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')))
    await expect(new ApiClient().rawRequest('/api/ping')).rejects.toThrow('network down')
    expect(rum.trackApiCall).toHaveBeenCalledWith('GET', '/api/ping', expect.any(Number), expect.any(Number), 'error', expect.any(Error), false)
  })
})
