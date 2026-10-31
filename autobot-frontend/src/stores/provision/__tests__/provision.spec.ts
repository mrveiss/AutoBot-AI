// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Provision store (#19834, #7096): resync from the backend, the WebSocket path, the polling
 * fallback and its pause on repeated failures (#19482), and reset. The adapter and the socket are fakes.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const api = vi.hoisted(() => ({ getProvisionStatus: vi.fn() }))
vi.mock('@/utils/slmApi', () => ({ slmApi: api, slmWsUrl: (route: string) => `ws://page/slm/api${route}` }))

import { useProvisionStore } from '../index'

class FakeSocket {
  static instances: FakeSocket[] = []
  static OPEN = 1
  static CONNECTING = 0
  readyState = FakeSocket.CONNECTING
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: ((err: unknown) => void) | null = null
  sent: string[] = []
  constructor(public url: string) {
    FakeSocket.instances.push(this)
  }
  send(data: string) {
    this.sent.push(data)
  }
  close() {
    this.readyState = 3
  }
  open() {
    this.readyState = FakeSocket.OPEN
    this.onopen?.()
  }
  emit(message: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify(message) })
  }
}

describe('provision store (#19834)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    api.getProvisionStatus.mockReset()
    FakeSocket.instances = []
    vi.stubGlobal('WebSocket', FakeSocket)
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('exposes exactly the surface of the SLM provision store it was ported from', () => {
    const surface = Object.keys(useProvisionStore()).filter((key) => !key.startsWith('_') && !key.startsWith('$'))
    expect(surface.sort()).toEqual([
      'completedPhases',
      'connectWs',
      'currentPhase',
      'currentTask',
      'disconnectWs',
      'elapsedFormatted',
      'elapsedSeconds',
      'error',
      'finishedAt',
      'isActive',
      'isComplete',
      'isFailed',
      'isRunning',
      'logs',
      'pollingPaused',
      'reset',
      'restoreFromBackend',
      'retryPolling',
      'stage',
      'start',
      'startedAt',
      'status',
      'wsConnected',
    ])
  })

  describe('restoreFromBackend', () => {
    it('replays the buffered lines and reconnects the socket for a running provision', async () => {
      api.getProvisionStatus.mockResolvedValue({
        status: 'running',
        lines: ['one', 'two'],
        total_lines: 2,
        error: null,
        elapsed_seconds: 61.4,
      })
      const store = useProvisionStore()
      await store.restoreFromBackend()

      expect(api.getProvisionStatus).toHaveBeenCalledWith(0)
      expect(store.status).toBe('running')
      expect(store.logs.map((l) => l.message)).toEqual(['one', 'two'])
      expect(store.elapsedSeconds).toBe(61)
      expect(store.elapsedFormatted).toBe('1m 1s')
      expect(FakeSocket.instances).toHaveLength(1)
      expect(FakeSocket.instances[0].url).toBe('ws://page/slm/api/ws/provision')
    })

    it('stays idle when the backend has nothing to resume', async () => {
      api.getProvisionStatus.mockResolvedValue({ status: 'idle', lines: [], total_lines: 0, error: null })
      const store = useProvisionStore()
      await store.restoreFromBackend()
      expect(store.status).toBe('idle')
      expect(store.isActive).toBe(false)
      expect(FakeSocket.instances).toHaveLength(0)
    })

    it('records a failed provision with its error', async () => {
      api.getProvisionStatus.mockResolvedValue({ status: 'failed', lines: [], total_lines: 0, error: 'playbook died' })
      const store = useProvisionStore()
      await store.restoreFromBackend()
      expect(store.isFailed).toBe(true)
      expect(store.error).toBe('playbook died')
      expect(store.finishedAt).not.toBeNull()
    })

    it('a failed read is swallowed and leaves the store idle', async () => {
      api.getProvisionStatus.mockRejectedValue(new Error('HTTP 503: revocation_check_unavailable'))
      const store = useProvisionStore()
      await expect(store.restoreFromBackend()).resolves.toBeUndefined()
      expect(store.status).toBe('idle')
    })
  })

  describe('live socket', () => {
    it('start() resets, runs, and connects; log and phase messages build the run', () => {
      const store = useProvisionStore()
      store.start()
      const socket = FakeSocket.instances[0]
      socket.open()
      expect(store.status).toBe('running')
      expect(store.wsConnected).toBe(true)

      socket.emit({ type: 'log', log_type: 'phase', message: 'Provision Phase 2: redis' })
      socket.emit({ type: 'log', log_type: 'task', message: 'install' })
      socket.emit({ type: 'log', log_type: 'heartbeat', message: 'Still running' })
      expect(store.currentPhase).toBe('2')
      expect(store.currentTask).toBe('Still running')
      expect(store.logs.map((l) => l.type)).toEqual(['phase', 'task'])

      socket.emit({ type: 'ping' })
      expect(socket.sent).toEqual(['pong'])
    })

    it('a completed status finishes the run and disconnects', () => {
      const store = useProvisionStore()
      store.start()
      const socket = FakeSocket.instances[0]
      socket.open()
      socket.emit({ type: 'log', log_type: 'phase', message: 'Provision Phase 1: base' })
      socket.emit({ type: 'status', status: 'completed', stage: 'done', elapsed_seconds: 12.6 })
      expect(store.isComplete).toBe(true)
      expect(store.elapsedSeconds).toBe(13)
      expect(store.completedPhases.has('1')).toBe(true)
      expect(store.wsConnected).toBe(false)
    })

    it('a failed status records the error as a log line', () => {
      const store = useProvisionStore()
      store.start()
      const socket = FakeSocket.instances[0]
      socket.open()
      socket.emit({ type: 'status', status: 'failed', error: 'boom' })
      expect(store.isFailed).toBe(true)
      expect(store.error).toBe('boom')
      expect(store.logs.at(-1)).toEqual({ type: 'error', message: 'boom' })
    })

    it('ignores a non-JSON message', () => {
      const store = useProvisionStore()
      store.start()
      const socket = FakeSocket.instances[0]
      socket.open()
      socket.onmessage?.({ data: 'not json' })
      expect(store.status).toBe('running')
    })
  })

  describe('polling fallback', () => {
    it('a socket that closes mid-run falls back to polling, which reads from the line cursor', async () => {
      api.getProvisionStatus.mockResolvedValue({ status: 'running', lines: ['a', 'b'], total_lines: 2, error: null })
      const store = useProvisionStore()
      store.start()
      const socket = FakeSocket.instances[0]
      socket.open()
      socket.onclose?.()

      // The poller reads once at once, then every interval, each from the line cursor.
      await vi.advanceTimersByTimeAsync(0)
      expect(api.getProvisionStatus).toHaveBeenLastCalledWith(0)
      expect(store.logs.map((l) => l.message)).toEqual(['a', 'b'])

      await vi.advanceTimersByTimeAsync(3000)
      expect(api.getProvisionStatus).toHaveBeenLastCalledWith(2)
    })

    it('a completed poll stops polling and reconnects for final messages', async () => {
      api.getProvisionStatus.mockResolvedValue({ status: 'completed', lines: [], total_lines: 0, error: null })
      const store = useProvisionStore()
      store.start()
      FakeSocket.instances[0].open()
      FakeSocket.instances[0].onclose?.()
      FakeSocket.instances[0].readyState = 3

      await vi.advanceTimersByTimeAsync(3000)
      expect(store.isComplete).toBe(true)
      expect(FakeSocket.instances).toHaveLength(2)
      const calls = api.getProvisionStatus.mock.calls.length
      await vi.advanceTimersByTimeAsync(9000)
      expect(api.getProvisionStatus.mock.calls.length).toBe(calls)
    })

    it('pauses after consecutive failed reads and resumes on retryPolling', async () => {
      api.getProvisionStatus.mockRejectedValue(new Error('HTTP 503'))
      const store = useProvisionStore()
      store.start()
      FakeSocket.instances[0].open()
      FakeSocket.instances[0].onclose?.()

      await vi.advanceTimersByTimeAsync(3000 * 5)
      expect(store.pollingPaused).toBe(true)
      const calls = api.getProvisionStatus.mock.calls.length
      await vi.advanceTimersByTimeAsync(9000)
      expect(api.getProvisionStatus.mock.calls.length).toBe(calls)

      api.getProvisionStatus.mockResolvedValue({ status: 'running', lines: [], total_lines: 0, error: null })
      store.retryPolling()
      expect(store.pollingPaused).toBe(false)
      await vi.advanceTimersByTimeAsync(3000)
      expect(api.getProvisionStatus.mock.calls.length).toBeGreaterThan(calls)
    })

    it('a socket that cannot be opened falls back to polling at once', async () => {
      class Broken {
        static OPEN = 1
        static CONNECTING = 0
        constructor() {
          throw new Error('no socket')
        }
      }
      vi.stubGlobal('WebSocket', Broken)
      api.getProvisionStatus.mockResolvedValue({ status: 'running', lines: [], total_lines: 0, error: null })
      const store = useProvisionStore()
      store.start()
      await vi.advanceTimersByTimeAsync(3000)
      expect(api.getProvisionStatus).toHaveBeenCalled()
    })
  })

  describe('stale heartbeat', () => {
    it('clears a task left over from a silent socket', () => {
      const store = useProvisionStore()
      store.start()
      const socket = FakeSocket.instances[0]
      socket.open()
      socket.emit({ type: 'log', log_type: 'heartbeat', message: 'Still running' })
      expect(store.currentTask).toBe('Still running')
      vi.advanceTimersByTime(40_000)
      expect(store.currentTask).toBe('')
    })
  })

  it('reset() returns to idle and drops the run', () => {
    const store = useProvisionStore()
    store.start()
    FakeSocket.instances[0].open()
    FakeSocket.instances[0].emit({ type: 'log', log_type: 'task', message: 'x' })
    store.reset()
    expect(store.status).toBe('idle')
    expect(store.logs).toEqual([])
    expect(store.startedAt).toBeNull()
    expect(store.wsConnected).toBe(false)
  })
})
