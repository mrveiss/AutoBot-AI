// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { useSseProgress } from '@/composables/transcriber/useSseProgress'

describe('useSseProgress', () => {
  let mockEventSource: any
  let onmessageHandler: ((event: MessageEvent) => void) | null = null
  let onerrorHandler: (() => void) | null = null

  beforeEach(() => {
    // Create a proper mock EventSource constructor
    mockEventSource = {
      close: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }

    // Mock the EventSource constructor
    vi.stubGlobal('EventSource', vi.fn(function EventSource(this: any, _url: string) {
      Object.defineProperty(mockEventSource, 'onmessage', {
        set: (handler) => { onmessageHandler = handler },
        get: () => onmessageHandler,
        configurable: true,
      })
      Object.defineProperty(mockEventSource, 'onerror', {
        set: (handler) => { onerrorHandler = handler },
        get: () => onerrorHandler,
        configurable: true,
      })
      return mockEventSource
    }))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
    onmessageHandler = null
    onerrorHandler = null
  })

  it('initialises with 0 progress and idle status', () => {
    const { percent, step, status } = useSseProgress(1)
    expect(percent.value).toBe(0)
    expect(step.value).toBe('')
    expect(status.value).toBe('idle')
  })

  it('creates EventSource with correct URL when connect is called', () => {
    const { connect } = useSseProgress(42)
    connect()
    expect(global.EventSource).toHaveBeenCalledWith(
      expect.stringContaining('/api/transcriber/recordings/42/progress')
    )
  })

  it('sets status to running when connection established', () => {
    const { status, connect } = useSseProgress(1)
    expect(status.value).toBe('idle')
    connect()
    expect(status.value).toBe('running')
  })

  it('updates percent and step from SSE message', () => {
    const { percent, step, connect } = useSseProgress(1)
    connect()

    const mockEvent = {
      data: JSON.stringify({ percent: 50, step: 'Processing audio' })
    } as MessageEvent

    onmessageHandler?.(mockEvent)

    expect(percent.value).toBe(50)
    expect(step.value).toBe('Processing audio')
  })

  it('sets status to complete and closes connection at 100%', () => {
    const { percent, status, connect } = useSseProgress(1)
    connect()

    const mockEvent = {
      data: JSON.stringify({ percent: 100, step: 'Done' })
    } as MessageEvent

    onmessageHandler?.(mockEvent)

    expect(percent.value).toBe(100)
    expect(status.value).toBe('complete')
    expect(mockEventSource.close).toHaveBeenCalled()
  })

  it('sets status to error and closes connection on error field', () => {
    const { status, connect } = useSseProgress(1)
    connect()

    const mockEvent = {
      data: JSON.stringify({ error: 'Processing failed' })
    } as MessageEvent

    onmessageHandler?.(mockEvent)

    expect(status.value).toBe('error')
    expect(mockEventSource.close).toHaveBeenCalled()
  })

  it('sets status to error and closes connection on onerror', () => {
    const { status, connect } = useSseProgress(1)
    connect()

    onerrorHandler?.()

    expect(status.value).toBe('error')
    expect(mockEventSource.close).toHaveBeenCalled()
  })

  it('ignores non-JSON messages (heartbeat)', () => {
    const { percent, step, connect } = useSseProgress(1)
    connect()

    const mockEvent = {
      data: 'heartbeat'
    } as MessageEvent

    onmessageHandler?.(mockEvent)

    expect(percent.value).toBe(0)
    expect(step.value).toBe('')
  })

  it('preserves previous values when message has partial data', () => {
    const { percent, step, connect } = useSseProgress(1)
    connect()

    const firstEvent = {
      data: JSON.stringify({ percent: 30, step: 'Step 1' })
    } as MessageEvent
    onmessageHandler?.(firstEvent)

    const secondEvent = {
      data: JSON.stringify({ percent: 50 })
    } as MessageEvent
    onmessageHandler?.(secondEvent)

    expect(percent.value).toBe(50)
    expect(step.value).toBe('Step 1') // Preserved from first event
  })

  it('closes connection when disconnect is called', () => {
    const { connect, disconnect } = useSseProgress(1)
    connect()
    disconnect()
    expect(mockEventSource.close).toHaveBeenCalled()
  })

  it('handles disconnect when not connected', () => {
    const { disconnect } = useSseProgress(1)
    // Should not throw when disconnecting without connect
    expect(() => disconnect()).not.toThrow()
  })
})
