// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #17530: a store document is the server's entry, with the server's id and full content.
import { describe, it, expect } from 'vitest'
import { entryToDocument } from '../knowledgeDocumentMapping'

describe('entryToDocument', () => {
  it('keeps the server id and content and marks the content complete', () => {
    const doc = entryToDocument({ id: 'srv-1', fact: 'full text', metadata: { title: 'T', tags: ['a'], category: 'c' } })
    expect(doc).toMatchObject({ id: 'srv-1', content: 'full text', title: 'T', contentComplete: true, category: 'c' })
  })

  it('falls back to fact_id and never mints an id', () => {
    expect(entryToDocument({ id: '', fact_id: 'f-9', content: 'x' })?.id).toBe('f-9')
    expect(entryToDocument({ id: '', content: 'x' })).toBeNull()
  })

  it('classifies uploads and web pages from metadata', () => {
    expect(entryToDocument({ id: '1', fact: 'x', metadata: { filename: 'a.pdf' } })?.type).toBe('upload')
    expect(entryToDocument({ id: '2', fact: 'x', metadata: { content_type: 'url' } })?.type).toBe('webpage')
  })
})
