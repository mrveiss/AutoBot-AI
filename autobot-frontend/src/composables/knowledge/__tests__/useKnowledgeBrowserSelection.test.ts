// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/** Selection and vectorize actions of the Knowledge Browser (#18244), against a fake vectorization state. */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import type { TreeNode } from '@/components/knowledge/TreeNodeComponent.vue'
import { useKnowledgeBrowserSelection } from '../useKnowledgeBrowserSelection'

function fakeVec(states: Record<string, string> = {}, selected: string[] = []) {
  const documentStates = ref(new Map(Object.entries(states).map(([id, status]) => [id, { status }]))) as never
  return {
    documentStates,
    selectedDocumentsList: ref(selected),
    getDocumentStatus: vi.fn(() => 'pending'),
    vectorizeDocument: vi.fn().mockResolvedValue({}),
    vectorizeBatch: vi.fn().mockResolvedValue({ succeeded: [], failed: [] }),
    vectorizeSelected: vi.fn().mockResolvedValue({ succeeded: [], failed: [] }),
  }
}

const folder: TreeNode = {
  id: 'f', name: 'f', type: 'folder', path: '/f',
  children: [
    { id: 'a', name: 'a', type: 'file', path: '/f/a' },
    { id: 'b', name: 'b', type: 'file', path: '/f/b' },
  ],
}

describe('useKnowledgeBrowserSelection', () => {
  it('vectorizes one document without opening the progress modal, and clears the busy flag', async () => {
    const vec = fakeVec()
    const sel = useKnowledgeBrowserSelection(vec as never)
    await sel.handleVectorizeDocument('a')
    expect(vec.vectorizeDocument).toHaveBeenCalledWith('a')
    expect(sel.isVectorizing.value).toBe(false)
    expect(sel.showProgressModal.value).toBe(false)
  })

  it('vectorizes a folder: only the files that are not vectorized, with the modal open', async () => {
    const vec = fakeVec({ a: 'vectorized' })
    const sel = useKnowledgeBrowserSelection(vec as never)
    await sel.handleVectorizeFolder(folder)
    expect(vec.vectorizeBatch).toHaveBeenCalledWith(['b'])
    expect(sel.showProgressModal.value).toBe(true)
  })

  it('does nothing for a folder whose files are all vectorized', async () => {
    const vec = fakeVec({ a: 'vectorized', b: 'vectorized' })
    const sel = useKnowledgeBrowserSelection(vec as never)
    await sel.handleVectorizeFolder(folder)
    expect(vec.vectorizeBatch).not.toHaveBeenCalled()
    expect(sel.showProgressModal.value).toBe(false)
  })

  it('vectorizes the selection with the modal open, and survives a failure', async () => {
    const vec = fakeVec()
    vec.vectorizeSelected.mockRejectedValueOnce(new Error('boom'))
    const sel = useKnowledgeBrowserSelection(vec as never)
    await expect(sel.vectorizeSelected()).resolves.toBeUndefined()
    expect(sel.showProgressModal.value).toBe(true)
    expect(sel.isVectorizing.value).toBe(false)
  })

  it('retries only the failed documents', async () => {
    const vec = fakeVec({ a: 'failed', b: 'vectorized', c: 'failed' })
    const sel = useKnowledgeBrowserSelection(vec as never)
    await sel.handleRetryFailed()
    expect(vec.vectorizeDocument.mock.calls.map((c) => c[0])).toEqual(['a', 'c'])
  })

  it('cancel closes the modal and stops the busy flag', () => {
    const sel = useKnowledgeBrowserSelection(fakeVec() as never)
    sel.showProgressModal.value = true
    sel.isVectorizing.value = true
    sel.handleCancelVectorization()
    expect([sel.showProgressModal.value, sel.isVectorizing.value]).toEqual([false, false])
  })

  it('counts the selected documents that still need vectorizing', () => {
    const vec = fakeVec({ a: 'vectorized', b: 'pending' }, ['a', 'b', 'c'])
    expect(useKnowledgeBrowserSelection(vec as never).eligibleCount.value).toBe(2)
  })
})
