// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * useToast — #14907 consolidation regression pins.
 *
 * This app's `useToast.ts` used to be an independent, trimmed implementation
 * (93 lines vs the main app's 184): `MAX_TOASTS=5` with no Tier-C protection,
 * so a burst of 6+ toasts silently evicted an unread persistent error. It is
 * now a re-export shim onto `@autobot/ui`'s canonical implementation (the
 * union of both prior versions). These tests pin the two capabilities this
 * app previously lacked, so a later "simplify by matching the smaller side"
 * change cannot silently drop them again.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { useToast, MAX_TOASTS } from './useToast'

function withSetup<T>(setup: () => T): T {
  let result!: T
  const Wrapper = defineComponent({
    setup() {
      result = setup()
      return {}
    },
    template: '<div />',
  })
  mount(Wrapper, { global: { stubs: { Teleport: true } } })
  return result
}

function resetSingleton(): void {
  withSetup(() => useToast().clearAllToasts())
}

describe('useToast shim (@autobot/ui) — capabilities the SLM copy used to lack', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    resetSingleton()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('MAX_TOASTS is the union value (3), not this app\'s former local value (5)', () => {
    expect(MAX_TOASTS).toBe(3)
  })

  it('never evicts a persistent (Tier C) error toast to make room', () => {
    const { showToast, toasts } = withSetup(() => useToast())

    showToast('error one', 'error', 0)
    showToast('error two', 'error', 0)
    showToast('error three', 'error', 0)
    // A fourth persistent error arrives with the stack already full of
    // Tier-C toasts — the SLM's old truncating implementation would have
    // dropped "error one" here.
    showToast('error four', 'error', 0)

    expect(toasts.value).toHaveLength(3)
    expect(toasts.value.map((t) => t.message)).toEqual([
      'error one',
      'error two',
      'error three',
    ])
  })

  it('queues an overflow persistent error and promotes it once a slot frees', () => {
    const { showToast, removeToast, toasts } = withSetup(() => useToast())

    const id1 = showToast('error one', 'error', 0)
    showToast('error two', 'error', 0)
    showToast('error three', 'error', 0)
    showToast('error four (queued)', 'error', 0)

    expect(toasts.value.map((t) => t.message)).not.toContain('error four (queued)')

    removeToast(id1)

    expect(toasts.value.map((t) => t.message)).toEqual([
      'error two',
      'error three',
      'error four (queued)',
    ])
  })
})
