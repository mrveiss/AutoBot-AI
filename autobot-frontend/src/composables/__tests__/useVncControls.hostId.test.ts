// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #22145: every chat Desktop control carries the selected host id, and the
 * endpoints are built from the injected canonical API base (#22144).
 */
import { describe, it, expect, vi } from 'vitest'
import { useVncControls } from '@autobot/vnc'
import { getApiBase } from '@/config/ssot-config'

function controls() {
  const request = vi.fn(async () => ({ status: 'success', message: 'ok' }))
  const api = useVncControls({ baseUrl: getApiBase(), hostId: 'host 1', request: request as never })
  return { api, request }
}

describe('useVncControls host targeting', () => {
  it('sends host_id with click, type, key, scroll, drag and clipboard', async () => {
    const { api, request } = controls()
    await api.mouseClick({ x: 1, y: 2 })
    await api.keyboardType('a')
    await api.specialKey('Return')
    await api.mouseScroll({ direction: 'up' })
    await api.mouseDrag({ x1: 0, y1: 0, x2: 1, y2: 1 })
    await api.syncClipboard('c')
    expect(request).toHaveBeenCalledTimes(6)
    for (const call of request.mock.calls as unknown as unknown[][]) {
      expect(call[1]).toMatch(new RegExp(`^${getApiBase()}/vnc/`))
      expect((call[2] as Record<string, unknown>).host_id).toBe('host 1')
    }
  })

  it('names the host in the screenshot query', async () => {
    const { api, request } = controls()
    await api.captureScreenshot()
    expect(request).toHaveBeenCalledWith('GET', `${getApiBase()}/vnc/screenshot?host_id=host%201`)
  })
})
