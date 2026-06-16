// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * Unit tests for useInlineEdit composable (#9205).
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useInlineEdit } from '../useInlineEdit'

const { mockLoggerError } = vi.hoisted(() => ({ mockLoggerError: vi.fn() }))

// Plain function (not vi.fn) so a global mockReset cannot wipe the factory.
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({
    error: mockLoggerError,
    warn: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
    log: vi.fn(),
  }),
}))

interface Item {
  id: number
  text: string
}

describe('useInlineEdit', () => {
  let save: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockLoggerError.mockReset()
    save = vi.fn().mockResolvedValue(undefined)
  })

  function setup() {
    return useInlineEdit<Item>((item) => item.text, save as (item: Item, value: string) => Promise<void>)
  }

  it('initialises with no item being edited', () => {
    const { editingId, editText } = setup()
    expect(editingId.value).toBeNull()
    expect(editText.value).toBe('')
  })

  it('startEdit sets editingId and seeds editText from getValue', () => {
    const { editingId, editText, startEdit } = setup()
    startEdit({ id: 7, text: 'hello' })
    expect(editingId.value).toBe(7)
    expect(editText.value).toBe('hello')
  })

  it('saveEdit skips save when value is unchanged and resets editingId', async () => {
    const { editingId, startEdit, saveEdit } = setup()
    const item = { id: 1, text: 'same' }
    startEdit(item)
    await saveEdit(item)
    expect(save).not.toHaveBeenCalled()
    expect(editingId.value).toBeNull()
  })

  it('saveEdit calls save with item and new value, then resets editingId', async () => {
    const { editingId, editText, startEdit, saveEdit } = setup()
    const item = { id: 2, text: 'old' }
    startEdit(item)
    editText.value = 'new'
    await saveEdit(item)
    expect(save).toHaveBeenCalledOnce()
    expect(save).toHaveBeenCalledWith(item, 'new')
    expect(editingId.value).toBeNull()
  })

  it('keeps editingId set while save is pending', async () => {
    let resolveSave!: () => void
    save.mockImplementation(() => new Promise<void>((resolve) => { resolveSave = resolve }))
    const { editingId, editText, startEdit, saveEdit } = setup()
    const item = { id: 3, text: 'old' }
    startEdit(item)
    editText.value = 'new'
    const pending = saveEdit(item)
    expect(editingId.value).toBe(3)
    resolveSave()
    await pending
    expect(editingId.value).toBeNull()
  })

  it('logs save failures and still resets editingId without rethrowing', async () => {
    const failure = new Error('boom')
    save.mockRejectedValue(failure)
    const { editingId, editText, startEdit, saveEdit } = setup()
    const item = { id: 4, text: 'old' }
    startEdit(item)
    editText.value = 'new'
    await expect(saveEdit(item)).resolves.toBeUndefined()
    expect(mockLoggerError).toHaveBeenCalledWith('Failed to save inline edit', failure)
    expect(editingId.value).toBeNull()
  })

  it('allows cancelling by resetting editingId externally (escape key pattern)', () => {
    const { editingId, startEdit } = setup()
    startEdit({ id: 5, text: 'x' })
    editingId.value = null
    expect(editingId.value).toBeNull()
  })
})
