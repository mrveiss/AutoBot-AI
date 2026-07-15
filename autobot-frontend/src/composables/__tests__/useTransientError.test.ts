// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { effectScope } from 'vue'
import { useTransientError } from '../useTransientError'

describe('useTransientError', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('show() sets message', () => {
    const { message, show } = useTransientError()
    show('Test error')
    expect(message.value).toBe('Test error')
  })

  it('clears message after ttl', () => {
    const { message, show } = useTransientError(1000)
    show('Test error')
    vi.advanceTimersByTime(1000)
    expect(message.value).toBeNull()
  })

  it('repeated show() resets the timer', () => {
    const { message, show } = useTransientError(1000)
    show('First error')
    vi.advanceTimersByTime(800)
    show('Second error')
    vi.advanceTimersByTime(800) // 1600ms total, but timer was reset at 800ms
    expect(message.value).toBe('Second error')
    vi.advanceTimersByTime(200) // now 1000ms since last show
    expect(message.value).toBeNull()
  })

  it('clear() clears message immediately', () => {
    const { message, show, clear } = useTransientError()
    show('error')
    clear()
    expect(message.value).toBeNull()
  })

  it('message starts null', () => {
    const { message } = useTransientError()
    expect(message.value).toBeNull()
  })

  it('cancels the pending timer when the effect scope disposes', () => {
    const scope = effectScope()
    const api = scope.run(() => useTransientError())!
    api.show('error')
    scope.stop()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('does not warn when used outside an effect scope', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    useTransientError().show('error')
    expect(warn).not.toHaveBeenCalled()
    warn.mockRestore()
  })
})
