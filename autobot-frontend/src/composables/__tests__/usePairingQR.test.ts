// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Unit tests for the usePairingQR composable (#13810).
 *
 * This composable is the single implementation of the device-pairing challenge.
 * Two other surfaces used to carry their own copy; both now delegate here, so
 * these tests are what stops the behaviour from silently regressing:
 * - the QR encodes the `autobot://pair?token=` deep link, NOT the bare token
 *   (a previous duplicate encoded the raw token, which the app cannot act on)
 * - the countdown comes from the backend's expires_in_seconds, not a hardcoded TTL
 * - reset() stops both intervals, so cancelling a flow cannot leak timers
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { usePairingQR } from '../usePairingQR'

const OLD = '2026-01-01T00:00:00.000Z'

const mockGet = vi.fn()
vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
  },
}))

const mockToDataURL = vi.fn()
vi.mock('qrcode', () => ({
  default: {
    toDataURL: (...args: unknown[]) => mockToDataURL(...args),
  },
}))

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api',
}))

describe('usePairingQR', () => {
  // fetchChallenge() snapshots the existing devices first, then asks for the
  // challenge, so the mock has to answer both in order.
  function primeFetch(opts: { existing?: unknown[]; ttl?: number; token?: string } = {}) {
    mockGet
      .mockResolvedValueOnce({ devices: opts.existing ?? [] })
      .mockResolvedValueOnce({
        challenge_token: opts.token ?? 'tok-abc',
        expires_in_seconds: opts.ttl ?? 300,
      })
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    mockToDataURL.mockResolvedValue('data:image/png;base64,STUB')
    mockGet.mockResolvedValue({ devices: [] })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('encodes the pairing deep link, not the bare challenge token', async () => {
    primeFetch()
    const { fetchChallenge, qrDataUrl } = usePairingQR()

    await fetchChallenge()

    expect(mockToDataURL).toHaveBeenCalledTimes(1)
    const [encoded] = mockToDataURL.mock.calls[0]
    // The exact contract the mobile app scans. Encoding just 'tok-abc' here
    // produces a QR that scans to a meaningless string.
    expect(encoded).toBe('autobot://pair?token=tok-abc')
    expect(qrDataUrl.value).toBe('data:image/png;base64,STUB')
  })

  it('drives the countdown from the backend TTL rather than a fixed value', async () => {
    primeFetch({ token: 't', ttl: 90 })
    const { fetchChallenge, formattedTime, isExpired } = usePairingQR()

    await fetchChallenge()
    expect(formattedTime.value).toBe('1:30')
    expect(isExpired.value).toBe(false)

    await vi.advanceTimersByTimeAsync(31_000)
    expect(formattedTime.value).toBe('0:59')

    await vi.advanceTimersByTimeAsync(59_000)
    expect(isExpired.value).toBe(true)
    expect(formattedTime.value).toBe('0:00')
  })

  it('reports paired when a device id appears that was not there before', async () => {
    primeFetch({ existing: [{ id: 'd0', device_name: 'Old', created_at: OLD }] })
    const { fetchChallenge, isPaired } = usePairingQR()
    await fetchChallenge()
    expect(isPaired.value).toBe(false)

    mockGet.mockResolvedValue({
      devices: [
        { id: 'd0', device_name: 'Old', created_at: OLD },
        { id: 'd1', device_name: 'Phone', created_at: new Date().toISOString() },
      ],
    })
    await vi.advanceTimersByTimeAsync(2_000)

    expect(isPaired.value).toBe(true)
  })

  it('does not re-report a device that was already paired before this challenge', async () => {
    // The bug this replaces: matching on "created less than 10s ago" meant that
    // opening the dialog again right after a successful pair auto-reported
    // success without anything being scanned.
    const justPaired = new Date().toISOString()
    primeFetch({ existing: [{ id: 'd1', device_name: 'Phone', created_at: justPaired }] })
    const { fetchChallenge, isPaired } = usePairingQR()
    await fetchChallenge()

    mockGet.mockResolvedValue({
      devices: [{ id: 'd1', device_name: 'Phone', created_at: justPaired }],
    })
    await vi.advanceTimersByTimeAsync(6_000)

    expect(isPaired.value).toBe(false)
  })

  it('stops polling once the challenge expires', async () => {
    primeFetch({ ttl: 3 })
    const { fetchChallenge, isExpired } = usePairingQR()
    await fetchChallenge()

    await vi.advanceTimersByTimeAsync(4_000)
    expect(isExpired.value).toBe(true)

    const callsAtExpiry = mockGet.mock.calls.length
    await vi.advanceTimersByTimeAsync(20_000)
    // An expired challenge can never be redeemed; polling on is pure noise.
    expect(mockGet.mock.calls.length).toBe(callsAtExpiry)
  })

  it('stops the countdown and the pairing poll on reset', async () => {
    primeFetch()
    const { fetchChallenge, reset, qrDataUrl } = usePairingQR()
    await fetchChallenge()

    const callsAfterFetch = mockGet.mock.calls.length
    reset()
    expect(qrDataUrl.value).toBeNull()

    await vi.advanceTimersByTimeAsync(10_000)
    // No further polling: cancelling a flow must not leave intervals running.
    expect(mockGet.mock.calls.length).toBe(callsAfterFetch)
  })

  it('surfaces an error instead of a half-built QR when the challenge fails', async () => {
    mockGet.mockReset()
    mockGet.mockRejectedValue(new Error('boom'))
    const { fetchChallenge, error, qrDataUrl, loading } = usePairingQR()

    await fetchChallenge()

    expect(error.value).toBeTruthy()
    expect(qrDataUrl.value).toBeNull()
    expect(loading.value).toBe(false)
  })
})
