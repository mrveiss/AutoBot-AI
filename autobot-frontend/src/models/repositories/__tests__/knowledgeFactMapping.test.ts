// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { describe, it, expect } from 'vitest'
import { factToDocument } from '../knowledgeFactMapping'

const base = { key: 'fact:1', content: 'body' }

describe('factToDocument', () => {
  it('parses a valid created_at', () => {
    const doc = factToDocument('1', { ...base, created_at: '2026-01-02T00:00:00Z' })
    expect(doc.createdAt.toISOString()).toBe('2026-01-02T00:00:00.000Z')
  })

  it('falls back to the epoch for a missing or unparsable created_at, never Invalid Date', () => {
    for (const created_at of [undefined, 'not-a-date']) {
      const doc = factToDocument('1', { ...base, created_at })
      expect(Number.isNaN(doc.createdAt.getTime())).toBe(false)
      expect(doc.createdAt.getTime()).toBe(0)
      expect(doc.updatedAt.getTime()).toBe(0)
    }
  })

  it('keeps only string tags', () => {
    const doc = factToDocument('1', { ...base, metadata: { tags: ['a', 1, null, 'b', { x: 1 }] } })
    expect(doc.tags).toEqual(['a', 'b'])
  })

  it('defaults tags to [] when not an array', () => {
    expect(factToDocument('1', { ...base, metadata: { tags: 'a' } }).tags).toEqual([])
  })
})
