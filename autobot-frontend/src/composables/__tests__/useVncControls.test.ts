// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Unit tests for useVncControls session_id threading (#12002 review fix).
 *
 * The backend gates /vnc/click|type|key|scroll|drag on the desktop
 * control-lock by session_id (owner-aware). This composable must actually
 * send session_id in the request body rather than silently relying on the
 * backend schema's own "default" fallback.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockPost = vi.fn(async (..._args: unknown[]) => ({ status: 'success', message: 'ok' }))

vi.mock('@/utils/ApiClient', () => ({
  default: {
    post: (...args: unknown[]) => mockPost(...args),
    get: vi.fn(async () => ({ status: 'success', message: 'ok', image_data: '' }))
  }
}))

import { useVncControls } from '../useVncControls'

describe('useVncControls session_id threading', () => {
  beforeEach(() => {
    mockPost.mockClear()
  })

  it('defaults session_id to "default" when none is provided', async () => {
    const { mouseClick } = useVncControls()
    await mouseClick({ x: 1, y: 2 })

    expect(mockPost).toHaveBeenCalledWith('/api/vnc/click', { x: 1, y: 2, session_id: 'default' })
  })

  it('threads an explicit session_id through mouseClick/keyboardType/specialKey/scroll/drag', async () => {
    const { mouseClick, keyboardType, specialKey, mouseScroll, mouseDrag } = useVncControls('chat-42')

    await mouseClick({ x: 1, y: 2 })
    expect(mockPost).toHaveBeenLastCalledWith('/api/vnc/click', { x: 1, y: 2, session_id: 'chat-42' })

    await keyboardType('hello')
    expect(mockPost).toHaveBeenLastCalledWith('/api/vnc/type', { text: 'hello', session_id: 'chat-42' })

    await specialKey('Return')
    expect(mockPost).toHaveBeenLastCalledWith('/api/vnc/key', { key: 'Return', session_id: 'chat-42' })

    await mouseScroll({ direction: 'up' })
    expect(mockPost).toHaveBeenLastCalledWith('/api/vnc/scroll', { direction: 'up', session_id: 'chat-42' })

    await mouseDrag({ x1: 0, y1: 0, x2: 5, y2: 5 })
    expect(mockPost).toHaveBeenLastCalledWith('/api/vnc/drag', { x1: 0, y1: 0, x2: 5, y2: 5, session_id: 'chat-42' })
  })
})
