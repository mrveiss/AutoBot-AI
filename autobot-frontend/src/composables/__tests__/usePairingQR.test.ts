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
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    mockToDataURL.mockResolvedValue('data:image/png;base64,STUB')
    mockGet.mockResolvedValue({ challenge_token: 'tok-abc', expires_in_seconds: 300 })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('encodes the pairing deep link, not the bare challenge token', async () => {
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
    mockGet.mockResolvedValue({ challenge_token: 't', expires_in_seconds: 90 })
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

  it('reports paired once a freshly created device appears', async () => {
    const { fetchChallenge, isPaired } = usePairingQR()
    await fetchChallenge()
    expect(isPaired.value).toBe(false)

    mockGet.mockResolvedValue({
      devices: [{ id: 'd1', device_name: 'Phone', created_at: new Date().toISOString() }],
    })
    await vi.advanceTimersByTimeAsync(2_000)

    expect(isPaired.value).toBe(true)
  })

  it('ignores devices that were already paired long ago', async () => {
    const { fetchChallenge, isPaired } = usePairingQR()
    await fetchChallenge()

    const old = new Date(Date.now() - 60_000).toISOString()
    mockGet.mockResolvedValue({ devices: [{ id: 'd0', device_name: 'Old', created_at: old }] })
    await vi.advanceTimersByTimeAsync(4_000)

    // A pre-existing device must not be mistaken for the one just paired.
    expect(isPaired.value).toBe(false)
  })

  it('stops the countdown and the pairing poll on reset', async () => {
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
    mockGet.mockRejectedValue(new Error('boom'))
    const { fetchChallenge, error, qrDataUrl, loading } = usePairingQR()

    await fetchChallenge()

    expect(error.value).toBeTruthy()
    expect(qrDataUrl.value).toBeNull()
    expect(loading.value).toBe(false)
  })
})
