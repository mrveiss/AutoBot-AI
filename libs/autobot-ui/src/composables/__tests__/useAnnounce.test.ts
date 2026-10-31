// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// useAnnounce behavioral tests (#18240): one body-level live region,
// clear-then-set on the next frame, priority switch.

import { describe, it, expect, vi, afterEach } from 'vitest'
import { useAnnounce, LIVE_REGION_ID } from '../useAnnounce'

describe('useAnnounce', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('creates one polite status region and reuses it', () => {
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => cb(0))
    const { announce } = useAnnounce()
    announce('one')
    announce('two')
    const regions = document.querySelectorAll(`#${LIVE_REGION_ID}`)
    expect(regions).toHaveLength(1)
    expect(regions[0].getAttribute('role')).toBe('status')
    expect(regions[0].getAttribute('aria-atomic')).toBe('true')
    expect(regions[0].getAttribute('aria-live')).toBe('polite')
    expect(regions[0].textContent).toBe('two')
  })

  it('clears first and sets the message on the next frame', () => {
    let frame: FrameRequestCallback = () => {}
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      frame = cb
      return 1
    })
    const { announce } = useAnnounce()
    announce('hello')
    const region = document.getElementById(LIVE_REGION_ID) as HTMLElement
    expect(region.textContent).toBe('')
    frame(0)
    expect(region.textContent).toBe('hello')
  })

  it('applies the assertive priority', () => {
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => cb(0))
    useAnnounce().announce('now', 'assertive')
    expect(document.getElementById(LIVE_REGION_ID)?.getAttribute('aria-live')).toBe('assertive')
  })
})
