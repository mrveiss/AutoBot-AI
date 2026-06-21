// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { describe, it, expect } from 'vitest'
import { formatCategoryName } from '@/utils/formatHelpers'

describe('formatCategoryName', () => {
  it('title-cases underscore/hyphen separated categories', () => {
    expect(formatCategoryName('system_commands')).toBe('System Commands')
    expect(formatCategoryName('auto-bot-docs')).toBe('Auto Bot Docs')
  })

  it('returns empty string for falsy input', () => {
    expect(formatCategoryName('')).toBe('')
    expect(formatCategoryName(undefined as unknown as string)).toBe('')
    expect(formatCategoryName(null as unknown as string)).toBe('')
  })

  // #10208: backend-sourced category values aren't guaranteed strings at
  // runtime; the formatter must coerce, not throw "split is not a function".
  it('does not throw on non-string input (coerces via String)', () => {
    expect(() => formatCategoryName(42 as unknown as string)).not.toThrow()
    expect(formatCategoryName(42 as unknown as string)).toBe('42')
    expect(() => formatCategoryName({ a: 1 } as unknown as string)).not.toThrow()
    expect(() => formatCategoryName(['x', 'y'] as unknown as string)).not.toThrow()
  })
})
