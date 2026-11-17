// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #21584: a refresh that read only part of the fleet says so; a refresh that read all of it, or none of it,
// does not raise the partial-list notice.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { PartialListError } from '@/utils/fetchAllPages'

const fetchNodes = vi.fn()
const showToast = vi.fn()

vi.mock('@/stores/fleet', () => ({ useFleetStore: () => ({ fetchNodes }) }))
vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string, params?: Record<string, unknown>) => `${key}:${JSON.stringify(params ?? {})}` }),
}))
vi.mock('@autobot/ui', () => ({
  createLogger: () => ({ error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() }),
  useToast: () => ({ showToast }),
}))

import { useFleetRefresh } from './useFleetRefresh'

describe('useFleetRefresh (#21584)', () => {
  beforeEach(() => {
    fetchNodes.mockReset()
    showToast.mockReset()
  })

  it('a complete refresh shows no notice', async () => {
    fetchNodes.mockResolvedValue(undefined)
    await useFleetRefresh().refreshFleet()
    expect(showToast).not.toHaveBeenCalled()
  })

  it('a partial refresh tells the operator how many of how many nodes are shown', async () => {
    fetchNodes.mockRejectedValue(new PartialListError(Array.from({ length: 100 }, (_, i) => i), 250, new Error('504')))
    await useFleetRefresh().refreshFleet()

    expect(showToast).toHaveBeenCalledTimes(1)
    const [message, kind] = showToast.mock.calls[0] as [string, string]
    expect(message).toBe('fleetOverview.incompleteList:{"loaded":100,"total":250,"message":"504"}')
    expect(kind).toBe('error')
  })

  it('a refresh that read nothing is logged, not reported as a partial list', async () => {
    fetchNodes.mockRejectedValue(new Error('network down'))
    await expect(useFleetRefresh().refreshFleet()).resolves.toBeUndefined()
    expect(showToast).not.toHaveBeenCalled()
  })
})
