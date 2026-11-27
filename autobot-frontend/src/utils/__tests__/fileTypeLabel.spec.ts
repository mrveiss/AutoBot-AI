// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #22349: the Files tab Type column -- a known label, else the upper-cased extension, else "Unknown".
import { describe, it, expect } from 'vitest'
import { getFileType } from '../fileTypeLabel'

const t = (key: string, params?: Record<string, unknown>) => (params ? `${key}:${params.ext}` : key)

describe('getFileType (#22349)', () => {
  it('maps a known extension case-insensitively', () => {
    expect(getFileType('report.JSON', t)).toBe('fileBrowser.fileType.json')
  })
  it('upper-cases an unknown extension', () => {
    expect(getFileType('data.xyz', t)).toBe('fileBrowser.fileType.extension:XYZ')
  })
  it('is Unknown when the name has no extension, even if it spells one', () => {
    expect(getFileType('json', t)).toBe('fileBrowser.fileType.unknown')
    expect(getFileType('notes.', t)).toBe('fileBrowser.fileType.unknown')
  })
})
