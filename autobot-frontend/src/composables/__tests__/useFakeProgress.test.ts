// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Unit tests for useFakeProgress (#5237)
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { effectScope } from 'vue'

import { useFakeProgress } from '../useFakeProgress'

describe('useFakeProgress', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('starts in idle state with progress=0 and isRunning=false', () => {
    const { progress, isRunning } = useFakeProgress()
    expect(progress.value).toBe(0)
    expect(isRunning.value).toBe(false)
  })

  it('start() sets isRunning=true and progress ticks up by step', () => {
    const { start, progress, isRunning } = useFakeProgress({
      target: 100,
      intervalMs: 50,
      step: 1
    })

    start()
    expect(isRunning.value).toBe(true)
    expect(progress.value).toBe(0)

    vi.advanceTimersByTime(50)
    expect(progress.value).toBe(1)

    vi.advanceTimersByTime(50)
    expect(progress.value).toBe(2)

    vi.advanceTimersByTime(50 * 3)
    expect(progress.value).toBe(5)
  })

  it('progress caps at cap and never exceeds it via ticking', () => {
    const { start, progress } = useFakeProgress({
      target: 10,
      intervalMs: 10,
      step: 1,
      cap: 4
    })

    start()
    // Advance enough ticks to exceed cap many times over
    vi.advanceTimersByTime(10 * 50)
    expect(progress.value).toBe(4)
  })

  it('cap defaults to target - 1', () => {
    const { start, progress } = useFakeProgress({
      target: 5,
      intervalMs: 10,
      step: 1
    })

    start()
    vi.advanceTimersByTime(10 * 100)
    expect(progress.value).toBe(4) // target - 1
  })

  it('finish() sets progress=target and isRunning=false', () => {
    const { start, finish, progress, isRunning } = useFakeProgress({
      target: 50,
      intervalMs: 100
    })

    start()
    vi.advanceTimersByTime(300) // progress around 3
    expect(isRunning.value).toBe(true)

    finish()
    expect(progress.value).toBe(50)
    expect(isRunning.value).toBe(false)

    // No more ticking after finish
    vi.advanceTimersByTime(1000)
    expect(progress.value).toBe(50)
  })

  it('stop() halts at current value without completing', () => {
    const { start, stop, progress, isRunning } = useFakeProgress({
      target: 100,
      intervalMs: 10,
      step: 1
    })

    start()
    vi.advanceTimersByTime(50) // progress=5
    expect(progress.value).toBe(5)

    stop()
    expect(isRunning.value).toBe(false)
    expect(progress.value).toBe(5) // held, not zeroed

    vi.advanceTimersByTime(1000)
    expect(progress.value).toBe(5)
  })

  it('reset() zeroes progress and halts', () => {
    const { start, reset, progress, isRunning } = useFakeProgress({
      target: 100,
      intervalMs: 10,
      step: 1
    })

    start()
    vi.advanceTimersByTime(70)
    expect(progress.value).toBe(7)

    reset()
    expect(progress.value).toBe(0)
    expect(isRunning.value).toBe(false)

    vi.advanceTimersByTime(1000)
    expect(progress.value).toBe(0)
  })

  it('respects custom target, intervalMs, step, and cap', () => {
    const { start, progress } = useFakeProgress({
      target: 200,
      intervalMs: 25,
      step: 10,
      cap: 150
    })

    start()
    vi.advanceTimersByTime(25)
    expect(progress.value).toBe(10)

    vi.advanceTimersByTime(25 * 20)
    expect(progress.value).toBe(150) // capped

    vi.advanceTimersByTime(25 * 5)
    expect(progress.value).toBe(150) // stays capped
  })

  it('start() after start() resets to 0 and restarts', () => {
    const { start, progress } = useFakeProgress({
      target: 100,
      intervalMs: 10,
      step: 1
    })

    start()
    vi.advanceTimersByTime(50)
    expect(progress.value).toBe(5)

    // Restart mid-way
    start()
    expect(progress.value).toBe(0)

    vi.advanceTimersByTime(20)
    expect(progress.value).toBe(2)
  })

  it('Math.min guards step overshoot above cap', () => {
    // step > (cap - progress) near the end should not overshoot
    const { start, progress } = useFakeProgress({
      target: 10,
      intervalMs: 10,
      step: 7,
      cap: 10
    })

    start()
    vi.advanceTimersByTime(10)
    expect(progress.value).toBe(7)

    vi.advanceTimersByTime(10)
    expect(progress.value).toBe(10) // 7 + 7 capped to 10, not 14
  })

  it('auto-cleans up when owning effect scope is disposed', () => {
    const scope = effectScope()
    let handle: ReturnType<typeof useFakeProgress>
    scope.run(() => {
      handle = useFakeProgress({ target: 100, intervalMs: 10, step: 1 })
      handle.start()
    })

    vi.advanceTimersByTime(30)
    expect(handle!.progress.value).toBe(3)
    expect(handle!.isRunning.value).toBe(true)

    scope.stop()
    expect(handle!.isRunning.value).toBe(false)

    vi.advanceTimersByTime(1000)
    // Progress frozen after scope disposal (no more ticks)
    expect(handle!.progress.value).toBe(3)
  })

  it('can be called standalone outside a component scope without throwing', () => {
    // getCurrentScope() returns undefined outside effectScope; should not register onScopeDispose
    expect(() => {
      const { start, stop } = useFakeProgress()
      start()
      stop()
    }).not.toThrow()
  })

  it('start(overrides) applies per-run target/cap and finish() jumps to that target', () => {
    const { start, finish, progress } = useFakeProgress({
      target: 100,
      intervalMs: 10,
      step: 1
    })

    start({ target: 42 })
    vi.advanceTimersByTime(10 * 100)
    expect(progress.value).toBe(41) // override cap = 42 - 1

    finish()
    expect(progress.value).toBe(42)
  })

  it('start(overrides) accepts explicit cap alongside target', () => {
    const { start, progress } = useFakeProgress({ intervalMs: 10, step: 1 })

    start({ target: 50, cap: 10 })
    vi.advanceTimersByTime(10 * 50)
    expect(progress.value).toBe(10)
  })

  it('start() without overrides reverts to constructor defaults after a prior override run', () => {
    const { start, finish, progress } = useFakeProgress({
      target: 100,
      intervalMs: 10,
      step: 1
    })

    start({ target: 10 })
    vi.advanceTimersByTime(10 * 50)
    expect(progress.value).toBe(9)

    // Restart with no overrides — should use target=100, cap=99
    start()
    vi.advanceTimersByTime(10 * 200)
    expect(progress.value).toBe(99)

    finish()
    expect(progress.value).toBe(100)
  })
})
