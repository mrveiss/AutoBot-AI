// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useCanvasAutoSave } from '@/composables/useCanvasAutoSave'
import { useCanvasStore } from '@/stores/useCanvasStore'

describe('useCanvasAutoSave', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    localStorage.clear()
  })

  afterEach(() => { vi.useRealTimers() })

  it('does not save immediately on change', () => {
    const store = useCanvasStore()
    const saveFn = vi.fn().mockResolvedValue(undefined)
    useCanvasAutoSave(saveFn)
    store.isDirty = true
    expect(saveFn).not.toHaveBeenCalled()
  })

  it('saves after debounce period', async () => {
    const store = useCanvasStore()
    store.setCanvas({ id: 'c1', title: '', cells: [], version: 1, updatedAt: '' })
    const saveFn = vi.fn().mockResolvedValue(undefined)
    useCanvasAutoSave(saveFn)
    store.isDirty = true
    await vi.advanceTimersByTimeAsync(1100)
    expect(saveFn).toHaveBeenCalled()
  })

  it('status becomes error when save throws', async () => {
    const store = useCanvasStore()
    store.setCanvas({ id: 'c1', title: '', cells: [], version: 1, updatedAt: '' })
    const saveFn = vi.fn().mockRejectedValue(new Error('network'))
    const { status } = useCanvasAutoSave(saveFn)
    store.isDirty = true
    await vi.advanceTimersByTimeAsync(1100)
    expect(status.value).toBe('error')
  })

  it('persists cells to localStorage after save', async () => {
    const store = useCanvasStore()
    store.setCanvas({ id: 'c1', title: 'T', cells: [], version: 1, updatedAt: '' })
    const saveFn = vi.fn().mockResolvedValue(undefined)
    useCanvasAutoSave(saveFn)
    store.isDirty = true
    await vi.advanceTimersByTimeAsync(1100)
    expect(localStorage.getItem('canvas:c1')).toBeTruthy()
  })

  it('loadFromLocalStorage returns null when no data', () => {
    const saveFn = vi.fn()
    const { loadFromLocalStorage } = useCanvasAutoSave(saveFn)
    expect(loadFromLocalStorage('nonexistent')).toBeNull()
  })
})
