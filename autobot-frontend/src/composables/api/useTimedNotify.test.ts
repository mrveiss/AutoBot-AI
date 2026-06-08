// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Unit tests for runTimed.
 *
 * Issue #5153 scope D-2.
 */

import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { runTimed } from './useTimedNotify'

describe('runTimed', () => {
  it('calls onSuccess with the resolved value and elapsed ms; does not call onFail', async () => {
    const onSuccess = vi.fn()
    const onFail = vi.fn()
    await runTimed(
      async () => {
        await new Promise((r) => setTimeout(r, 5))
        return 'ok'
      },
      onSuccess,
      onFail,
    )
    expect(onSuccess).toHaveBeenCalledTimes(1)
    const [value, elapsed] = onSuccess.mock.calls[0]!
    expect(value).toBe('ok')
    expect(typeof elapsed).toBe('number')
    expect(elapsed).toBeGreaterThanOrEqual(0)
    expect(onFail).not.toHaveBeenCalled()
  })

  it('on thrown Error: passes Error.message string plus the original error and elapsed ms', async () => {
    const onSuccess = vi.fn()
    const onFail = vi.fn()
    const boom = new Error('boom')
    await runTimed(
      async () => {
        throw boom
      },
      onSuccess,
      onFail,
    )
    expect(onSuccess).not.toHaveBeenCalled()
    expect(onFail).toHaveBeenCalledTimes(1)
    const [message, elapsed, originalErr] = onFail.mock.calls[0]!
    expect(message).toBe('boom')
    expect(typeof elapsed).toBe('number')
    expect(originalErr).toBe(boom)
  })

  it('on thrown non-Error: stringifies the thrown value', async () => {
    const onFail = vi.fn()
    await runTimed(
      async () => {
        throw 'plain string failure'  
      },
      vi.fn(),
      onFail,
    )
    const [message] = onFail.mock.calls[0]!
    expect(message).toBe('plain string failure')
  })

  it('loading ref: set to true before fn, false in success finally', async () => {
    const loading = ref(false)
    const seenDuring = ref<boolean | null>(null)
    await runTimed(
      async () => {
        seenDuring.value = loading.value
      },
      vi.fn(),
      vi.fn(),
      { loadingRef: loading },
    )
    expect(seenDuring.value).toBe(true)
    expect(loading.value).toBe(false)
  })

  it('loading ref: reset to false even when fn throws', async () => {
    const loading = ref(false)
    await runTimed(
      async () => {
        throw new Error('fail')
      },
      vi.fn(),
      vi.fn(),
      { loadingRef: loading },
    )
    expect(loading.value).toBe(false)
  })

  it('loading ref: reset to false even when onSuccess throws', async () => {
    const loading = ref(false)
    const onSuccessBomb = () => {
      throw new Error('handler exploded')
    }
    await expect(
      runTimed(async () => 'ok', onSuccessBomb, vi.fn(), {
        loadingRef: loading,
      }),
    ).rejects.toThrow('handler exploded')
    expect(loading.value).toBe(false)
  })

  it('works without a loading ref (options omitted)', async () => {
    const onSuccess = vi.fn()
    await runTimed(async () => 42, onSuccess, vi.fn())
    expect(onSuccess).toHaveBeenCalledWith(42, expect.any(Number))
  })
})
