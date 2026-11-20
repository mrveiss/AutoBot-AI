// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { describe, it, expect } from 'vitest'
import { DEFAULT_FACT_CATEGORY, DEFAULT_FACT_TYPE, factToDocument } from '../knowledgeFactMapping'

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

  it('reads type and category from the backend like the list rows do (#21796)', () => {
    const doc = factToDocument('1', { ...base, metadata: { type: 'man_page', category: 'Systems' } })
    expect(doc.type).toBe('man_page')
    expect(doc.category).toBe('Systems')
    expect(doc.metadata?.factType).toBe('man_page')
  })

  it('falls back to the list rows defaults when type or category is absent or not a string', () => {
    for (const metadata of [undefined, {}, { type: 7, category: null }]) {
      const doc = factToDocument('1', { ...base, metadata })
      expect(doc.type).toBe(DEFAULT_FACT_TYPE)
      expect(doc.category).toBe(DEFAULT_FACT_CATEGORY)
      expect(doc.metadata?.factType).toBeUndefined()
    }
    expect([DEFAULT_FACT_TYPE, DEFAULT_FACT_CATEGORY]).toEqual(['document', 'General'])
  })
})
