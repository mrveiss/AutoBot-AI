// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #21584: the shell tells the operator once when the node list held is not the whole fleet, whichever
// view's fetchNodes() produced it; a complete list, or the same shortfall seen again, says nothing.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { reactive, nextTick } from 'vue'

const showToast = vi.fn()
const store = reactive({ incomplete: null as { read: number; total: number | null } | null, error: null as string | null })

vi.mock('@/stores/fleet', () => ({ useFleetStore: () => store }))
vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string, params?: Record<string, unknown>) => `${key}:${JSON.stringify(params ?? {})}` }),
}))
vi.mock('@autobot/ui', () => ({ useToast: () => ({ showToast }) }))

import { useFleetIncompleteNotice } from './useFleetIncompleteNotice'

describe('useFleetIncompleteNotice (#21584)', () => {
  beforeEach(() => {
    showToast.mockReset()
    store.incomplete = null
    store.error = null
  })

  it('a complete list shows no notice', async () => {
    useFleetIncompleteNotice()
    await nextTick()
    expect(showToast).not.toHaveBeenCalled()
  })

  it('a partial list says how many of how many nodes are shown, once', async () => {
    useFleetIncompleteNotice()
    store.error = 'Loaded 100 of 250: 504'
    store.incomplete = { read: 100, total: 250 }
    await nextTick()

    expect(showToast).toHaveBeenCalledTimes(1)
    const [message, kind] = showToast.mock.calls[0] as [string, string]
    expect(message).toBe('fleetOverview.incompleteList:{"loaded":100,"total":250,"message":"Loaded 100 of 250: 504"}')
    expect(kind).toBe('error')

    store.incomplete = { read: 100, total: 250 } // the next poll finds the same shortfall
    await nextTick()
    expect(showToast).toHaveBeenCalledTimes(1)
  })

  it('a different shortfall, or one after a recovery, is announced again', async () => {
    useFleetIncompleteNotice()
    store.incomplete = { read: 100, total: 250 }
    await nextTick()
    store.incomplete = { read: 200, total: 250 }
    await nextTick()
    store.incomplete = null
    await nextTick()
    store.incomplete = { read: 100, total: 250 }
    await nextTick()
    expect(showToast).toHaveBeenCalledTimes(3)
  })

  it('an unknown total is worded, not printed as null', async () => {
    useFleetIncompleteNotice()
    store.incomplete = { read: 100, total: null }
    await nextTick()
    expect(showToast.mock.calls[0][0]).toContain('"total":"fleetOverview.incompleteTotalUnknown:{}"')
  })
})
