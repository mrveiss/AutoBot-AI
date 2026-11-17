// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #21584: the shell tells the operator once when the node list held is not the whole fleet, whichever
// view's fetchNodes() produced it; a complete list, or the same shortfall seen again, says nothing.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { reactive, nextTick, effectScope } from 'vue'
import type { EffectScope } from 'vue'

const showToast = vi.fn()
type Shortfall = { read: number; total: number | null; reason: string }
const store = reactive({ incomplete: null as Shortfall | null })

vi.mock('@/stores/fleet', () => ({ useFleetStore: () => store }))
vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string, params?: Record<string, unknown>) => `${key}:${JSON.stringify(params ?? {})}` }),
}))
vi.mock('@autobot/ui', () => ({ useToast: () => ({ showToast }) }))

import { useFleetIncompleteNotice } from './useFleetIncompleteNotice'

// The composable's watcher lives in an effect scope per test and is stopped after it: outside a component
// nothing stops it, and the previous tests' watchers would otherwise answer the next test's changes too.
let scope: EffectScope
const mountNotice = (): void => {
  scope.run(useFleetIncompleteNotice)
}

describe('useFleetIncompleteNotice (#21584)', () => {
  beforeEach(() => {
    showToast.mockReset()
    store.incomplete = null
    scope = effectScope()
  })

  afterEach(() => {
    scope.stop()
  })

  it('a complete list shows no notice', async () => {
    mountNotice()
    await nextTick()
    expect(showToast).not.toHaveBeenCalled()
  })

  it('a partial list says how many of how many nodes are shown, once', async () => {
    mountNotice()
    store.incomplete = { read: 100, total: 250, reason: '504' }
    await nextTick()

    expect(showToast).toHaveBeenCalledTimes(1)
    const [message, kind] = showToast.mock.calls[0] as [string, string]
    expect(message).toBe('fleetOverview.incompleteList:{"loaded":100,"total":250,"message":"504"}')
    expect(kind).toBe('error')

    store.incomplete = { read: 100, total: 250, reason: '504' } // the next poll finds the same shortfall
    await nextTick()
    expect(showToast).toHaveBeenCalledTimes(1)
  })

  it('a different shortfall, or one after a recovery, is announced again', async () => {
    mountNotice()
    store.incomplete = { read: 100, total: 250, reason: '504' }
    await nextTick()
    store.incomplete = { read: 200, total: 250, reason: '504' }
    await nextTick()
    store.incomplete = null
    await nextTick()
    store.incomplete = { read: 100, total: 250, reason: '504' }
    await nextTick()
    expect(showToast).toHaveBeenCalledTimes(3)
  })

  it('an unknown total is worded, not printed as null', async () => {
    mountNotice()
    store.incomplete = { read: 100, total: null, reason: '504' }
    await nextTick()
    expect(showToast.mock.calls[0][0]).toContain('"total":"fleetOverview.incompleteTotalUnknown:{}"')
  })
})
