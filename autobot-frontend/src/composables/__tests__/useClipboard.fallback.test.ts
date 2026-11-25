// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// A rejected `navigator.clipboard.writeText` (denied permission, unfocused document,
// iframe policy) falls back to `execCommand('copy')` (#18243).
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useClipboard } from '../useClipboard'

const writeText = vi.fn()
const execCommand = vi.fn()

beforeEach(() => {
  writeText.mockReset().mockRejectedValue(new Error('Permission denied'))
  execCommand.mockReset()
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
  document.execCommand = execCommand
})

describe('useClipboard - fallback after a rejected writeText', () => {
  it('returns true when execCommand succeeds', async () => {
    execCommand.mockReturnValue(true)
    const clipboard = useClipboard()
    expect(await clipboard.copy('Test')).toBe(true)
    expect(execCommand).toHaveBeenCalledWith('copy')
    expect(clipboard.copied.value).toBe(true)
    expect(clipboard.error.value).toBeNull()
  })

  it('returns false with the writeText error when execCommand returns false', async () => {
    execCommand.mockReturnValue(false)
    const clipboard = useClipboard()
    expect(await clipboard.copy('Test')).toBe(false)
    expect(execCommand).toHaveBeenCalledWith('copy')
    expect((clipboard.error.value as Error).message).toBe('Permission denied')
  })

  it('falls back and fails when writeText rejects with undefined and execCommand returns false', async () => {
    writeText.mockRejectedValue(undefined)
    execCommand.mockReturnValue(false)
    const clipboard = useClipboard()
    expect(await clipboard.copy('Test')).toBe(false)
    expect(execCommand).toHaveBeenCalledWith('copy')
    expect(clipboard.copied.value).toBe(false)
  })

  it('returns false when execCommand throws', async () => {
    execCommand.mockImplementation(() => { throw new Error('boom') })
    expect(await useClipboard().copy('Test')).toBe(false)
  })
})
