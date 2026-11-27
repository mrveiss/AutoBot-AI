// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #17530: a store document is the server's entry, with the server's id and full content.
import { describe, it, expect } from 'vitest'
import { entryToDocument } from '../knowledgeDocumentMapping'
import type { KnowledgeEntry } from '@/types/api-contract'

const entry = (over: Partial<KnowledgeEntry>): KnowledgeEntry => ({
  id: 'srv-1', title: 'Untitled', content: '', source: 'unknown', category: 'general', type: 'document', ...over,
})

describe('entryToDocument', () => {
  it('keeps the server id and content and marks the content complete', () => {
    const doc = entryToDocument(entry({ content: 'full text', title: 'T', category: 'c', metadata: { tags: ['a'] } }))
    expect(doc).toMatchObject({ id: 'srv-1', content: 'full text', title: 'T', contentComplete: true, category: 'c', tags: ['a'] })
  })

  it('never mints an id', () => {
    expect(entryToDocument(entry({ id: '', content: 'x' }))).toBeNull()
  })

  it('classifies uploads and web pages from metadata', () => {
    expect(entryToDocument(entry({ metadata: { filename: 'a.pdf' } }))?.type).toBe('upload')
    expect(entryToDocument(entry({ metadata: { content_type: 'url' } }))?.type).toBe('webpage')
  })

  it('reads the served created_at and gives a missing date the epoch, not now', () => {
    expect(entryToDocument(entry({ created_at: '2026-01-02T03:04:05Z' }))?.createdAt.toISOString()).toBe('2026-01-02T03:04:05.000Z')
    expect(entryToDocument(entry({}))?.createdAt.getTime()).toBe(0)
  })
})
