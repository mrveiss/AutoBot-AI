// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #18718: clear-stuck is admin-gated. A refused (403) clear is reported as a refusal --
 * never retried, never shown as "another analysis is still running", never a successful no-op.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { HttpError } from '@autobot/ui'

const { post, fetchWithAuth } = vi.hoisted(() => ({ post: vi.fn(), fetchWithAuth: vi.fn() }))

vi.mock('@/utils/ApiClient', () => ({ default: { post, get: vi.fn() } }))
vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth }))
vi.mock('@/config/AppConfig.js', () => ({ default: { getServiceUrl: vi.fn(async () => 'http://backend') } }))

import { useBackgroundTask } from '@/composables/useBackgroundTask'
import { usePatternAnalysis } from '@/composables/usePatternAnalysis'
import { CLEAR_STUCK_FORBIDDEN_MESSAGE } from '@/composables/usePatternClearStuck'

const conflict = () => new Response('{}', { status: 409, statusText: 'Conflict' })

describe('a refused clear-stuck (#18718)', () => {
  beforeEach(() => {
    post.mockReset()
    fetchWithAuth.mockReset()
  })

  it('background task: a 409 whose clear is refused reports the refusal and does not retry', async () => {
    fetchWithAuth.mockResolvedValue(conflict())
    post.mockRejectedValue(new HttpError(403, 'Forbidden'))
    const task = useBackgroundTask('/api/x')
    expect(await task.start()).toBe(false)
    expect(task.error.value).toBe(CLEAR_STUCK_FORBIDDEN_MESSAGE)
    expect(fetchWithAuth).toHaveBeenCalledTimes(1)
  })

  it('contrast: a 409 whose clear succeeds retries once and still reports the conflict', async () => {
    fetchWithAuth.mockResolvedValue(conflict())
    post.mockResolvedValue({})
    const task = useBackgroundTask('/api/x')
    expect(await task.start()).toBe(false)
    expect(task.error.value).not.toBe(CLEAR_STUCK_FORBIDDEN_MESSAGE)
    expect(fetchWithAuth).toHaveBeenCalledTimes(2)
  })

  it('pattern analysis: a 409 whose clear is refused reports the refusal and does not retry', async () => {
    fetchWithAuth.mockResolvedValueOnce(conflict()).mockResolvedValueOnce(new Response('', { status: 403 }))
    const analysis = usePatternAnalysis()
    expect(await analysis.analyzePatterns('/src')).toBe(false)
    expect(analysis.error.value).toBe(CLEAR_STUCK_FORBIDDEN_MESSAGE)
    expect(fetchWithAuth).toHaveBeenCalledTimes(2)
  })

  it('manual clear: a refusal is its own result, distinct from clearing nothing', async () => {
    const analysis = usePatternAnalysis()
    post.mockRejectedValueOnce(new HttpError(403, 'Forbidden'))
    expect((await analysis.clearStuckTasks(true)).forbidden).toBe(true)
    post.mockResolvedValueOnce({ cleared_count: 0, message: 'none' })
    expect(await analysis.clearStuckTasks(true)).toEqual({ cleared: 0, message: 'none', forbidden: false })
  })
})
