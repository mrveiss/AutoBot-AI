// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// useImageCapture (#20644): the right browser API per source, a PNG file out, and every track stopped
// whether the frame was taken or not.

import { describe, it, expect, afterEach, vi } from 'vitest'
import { canCapture, captureImage } from '../useImageCapture'

function fakeStream() {
  const track = { stop: vi.fn() }
  return { track, stream: { getTracks: () => [track] } as unknown as MediaStream }
}

function setDevices(devices: Record<string, unknown> | undefined) {
  Object.defineProperty(navigator, 'mediaDevices', { value: devices, configurable: true })
}

function stubFrame(ok: boolean) {
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockImplementation(() =>
    ok ? Promise.resolve() : Promise.reject(new Error('play failed')),
  )
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined)
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
  vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation((done: BlobCallback) =>
    done(new Blob(['png'], { type: 'image/png' })),
  )
}

describe('useImageCapture (#20644)', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    setDevices(undefined)
  })

  it('reports which sources this browser can capture from', () => {
    setDevices(undefined)
    expect(canCapture('camera')).toBe(false)
    setDevices({ getUserMedia: vi.fn() })
    expect(canCapture('camera')).toBe(true)
    expect(canCapture('screen')).toBe(false)
  })

  it('takes a camera frame as a PNG file and stops the camera', async () => {
    const { track, stream } = fakeStream()
    const getUserMedia = vi.fn().mockResolvedValue(stream)
    setDevices({ getUserMedia })
    stubFrame(true)
    const file = await captureImage('camera', new Date('2026-11-16T10:00:00Z'))
    expect(getUserMedia).toHaveBeenCalledWith({ video: true })
    expect(file.type).toBe('image/png')
    expect(file.name).toBe('camera-2026-11-16T10-00-00-000Z.png')
    expect(track.stop).toHaveBeenCalled()
  })

  it('uses the screen-share prompt for a screen capture', async () => {
    const { stream } = fakeStream()
    const getDisplayMedia = vi.fn().mockResolvedValue(stream)
    setDevices({ getDisplayMedia })
    stubFrame(true)
    await captureImage('screen')
    expect(getDisplayMedia).toHaveBeenCalledWith({ video: true })
  })

  it('stops the stream and rejects when the frame cannot be taken', async () => {
    const { track, stream } = fakeStream()
    setDevices({ getUserMedia: vi.fn().mockResolvedValue(stream) })
    stubFrame(false)
    await expect(captureImage('camera')).rejects.toThrow('play failed')
    expect(track.stop).toHaveBeenCalled()
  })

  it('rejects when the user declines the prompt', async () => {
    setDevices({ getUserMedia: vi.fn().mockRejectedValue(new Error('Permission denied')) })
    await expect(captureImage('camera')).rejects.toThrow('Permission denied')
  })
})
