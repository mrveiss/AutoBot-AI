// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #17530 guard: `documents` is a projection of the server. It may be replaced by a server read
 * (`setDocuments`) and edited after the server accepted the change (update/delete); it may not
 * gain an entry the client made up. This reads the store and controller source so a new local
 * write fails here.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { setActivePinia, createPinia } from 'pinia'
import { useKnowledgeStore } from '../useKnowledgeStore'

const read = (rel: string) => readFileSync(new URL(rel, import.meta.url), 'utf-8')

describe('the document list is a server read (#17530)', () => {
  const store = read('../useKnowledgeStore.ts')

  it('has no push or client-minted id', () => {
    expect(store).not.toMatch(/documents\.value\.push\(/)
    expect(store).not.toMatch(/doc-\$\{Date\.now/)
    expect(store).not.toMatch(/documents[^\n]*Math\.random/)
    expect(store).not.toMatch(/function addDocument/)
  })

  it('assigns documents.value only inside setDocuments', () => {
    const assignments = store.match(/^\s*documents\.value\s*=/gm) ?? []
    expect(assignments).toHaveLength(1)
    expect(store.indexOf('documents.value = serverDocuments')).toBeGreaterThan(store.indexOf('function setDocuments'))
  })

  it('the controller never writes a document the server did not return', () => {
    const controller = read('../../models/controllers/KnowledgeController.ts')
    expect(controller).not.toMatch(/\.addDocument\(/)
    expect(controller).not.toMatch(/knowledgeStore\.documents\s*=/)
  })

  it('setDocuments replaces the list', () => {
    setActivePinia(createPinia())
    const s = useKnowledgeStore()
    s.setDocuments([{ id: 'a', title: 't', content: 'c', source: 's', type: 'document', tags: [], category: 'x', createdAt: new Date(), updatedAt: new Date() }])
    s.setDocuments([])
    expect(s.documents).toEqual([])
  })
})
