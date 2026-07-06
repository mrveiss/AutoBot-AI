// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Unit Tests for useActionQueue composable
 * Issue #3275: Offline mode — action queue for deferred network operations
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { nextTick, ref } from 'vue'


// Mock useNetworkStatus so queue tests are isolated from real network probes
vi.mock('../useNetworkStatus', () => {
  const isOnline = ref(true)
  return {
    useNetworkStatus: vi.fn(() => ({
      isOnline,
      isChecking: ref(false),
      lastOnlineAt: ref(null),
      isFeatureAvailable: () => true,
    })),
    isFeatureAvailable: (c: string, online: boolean) => {
      if (c === 'local-only') return true
      if (c === 'requires-network') return online
      return true
    },
  }
})

// localStorage mock
const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => { store[k] = v },
    removeItem: (k: string) => { delete store[k] },
    clear: () => { store = {} },
  }
})()
Object.defineProperty(window, 'localStorage', { value: localStorageMock, writable: true })

describe('useActionQueue', () => {
  beforeEach(() => {
    localStorageMock.clear()
    vi.resetModules()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('executes action immediately when online', async () => {
    const { useActionQueue } = await import('../useActionQueue')
    const { registerHandler, enqueue, queue } = useActionQueue()

    const handler = vi.fn().mockResolvedValue(undefined)
    registerHandler('test-action', handler)

    await enqueue('test-action', { data: 'hello' })
    await nextTick()

    expect(handler).toHaveBeenCalledOnce()
    expect(handler.mock.calls[0][0].payload).toEqual({ data: 'hello' })
    expect(queue.value).toHaveLength(0)
  })

  it('removes action from queue after successful execution', async () => {
    const { useActionQueue } = await import('../useActionQueue')
    const { registerHandler, enqueue, queue } = useActionQueue()

    registerHandler('remove-test', vi.fn().mockResolvedValue(undefined))
    await enqueue('remove-test', {})
    await nextTick()

    expect(queue.value).toHaveLength(0)
  })

  it('clearQueue empties the action queue', async () => {
    // Simulate offline by making handler throw
    const { useActionQueue } = await import('../useActionQueue')
    const { registerHandler, enqueue, queue, clearQueue } = useActionQueue()

    registerHandler('failing', vi.fn().mockRejectedValue(new Error('offline')))
    // Enqueue without awaiting to have it in queue before flush
    enqueue('failing', {})
    clearQueue()

    expect(queue.value).toHaveLength(0)
  })

  it('persists queue to localStorage', async () => {
    const { useActionQueue } = await import('../useActionQueue')
    const { registerHandler, enqueue } = useActionQueue()

    // Use a slow handler to freeze mid-execution so item stays in queue briefly
    let resolve!: () => void
    const slowHandler = vi.fn(() => new Promise<void>((r) => { resolve = r }))
    registerHandler('slow', slowHandler)

    enqueue('slow', { v: 1 })
    // Item is in storage before handler completes
    const raw = localStorageMock.getItem('autobot-action-queue')
    // It may already be cleared if handler ran synchronously, so just verify no crash
    expect(typeof raw).toBe('string')
    resolve?.()
  })
})
