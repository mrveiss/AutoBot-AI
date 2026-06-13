// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Unit Tests for useNetworkStatus composable
 * Issue #3275: Offline mode
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { isFeatureAvailable } from '../useNetworkStatus'

describe('isFeatureAvailable', () => {
  it('local-only features are always available offline', () => {
    expect(isFeatureAvailable('local-only', false)).toBe(true)
  })

  it('local-only features are available online', () => {
    expect(isFeatureAvailable('local-only', true)).toBe(true)
  })

  it('requires-network features are unavailable offline', () => {
    expect(isFeatureAvailable('requires-network', false)).toBe(false)
  })

  it('requires-network features are available online', () => {
    expect(isFeatureAvailable('requires-network', true)).toBe(true)
  })

  it('prefers-network features are available offline (degraded)', () => {
    expect(isFeatureAvailable('prefers-network', false)).toBe(true)
  })

  it('prefers-network features are available online', () => {
    expect(isFeatureAvailable('prefers-network', true)).toBe(true)
  })
})

describe('useNetworkStatus - browser events', () => {
  const onlineHandlers: EventListener[] = []
  const offlineHandlers: EventListener[] = []

  beforeEach(() => {
    vi.spyOn(window, 'addEventListener').mockImplementation(
      (type: string, handler: EventListenerOrEventListenerObject) => {
        if (type === 'online') onlineHandlers.push(handler as EventListener)
        if (type === 'offline') offlineHandlers.push(handler as EventListener)
      }
    )

    vi.spyOn(window, 'removeEventListener').mockImplementation(() => {})

    // Stub fetch to avoid real network calls
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200 }))
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    onlineHandlers.length = 0
    offlineHandlers.length = 0
  })

  it('registers online and offline event listeners on mount', async () => {
    const { useNetworkStatus } = await import('../useNetworkStatus')
    const { mount } = await import('@vue/test-utils')
    const { defineComponent } = await import('vue')

    const TestComp = defineComponent({
      setup() { useNetworkStatus() },
      template: '<div />'
    })

    const wrapper = mount(TestComp)
    expect(window.addEventListener).toHaveBeenCalledWith('online', expect.any(Function))
    expect(window.addEventListener).toHaveBeenCalledWith('offline', expect.any(Function))
    wrapper.unmount()
  })
})

// ========================================
// Scope-aware lifecycle (#5406)
// ========================================

describe('useNetworkStatus — scope-aware lifecycle (#5406)', () => {
  it('does not warn when used inside an effectScope (no component)', async () => {
    const { useNetworkStatus } = await import('../useNetworkStatus')
    const { effectScope } = await import('vue')

    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const scope = effectScope()
    scope.run(() => {
      useNetworkStatus()
    })
    scope.stop()
    expect(warn).not.toHaveBeenCalledWith(
      expect.stringContaining('no active component')
    )
    warn.mockRestore()
  })

  it('does not warn when called with no active scope at all', async () => {
    const { useNetworkStatus } = await import('../useNetworkStatus')

    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    useNetworkStatus()
    expect(warn).not.toHaveBeenCalledWith(
      expect.stringContaining('no active component')
    )
    warn.mockRestore()
  })
})
