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
    deselectAll: vi.fn(),
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

  it('vectorizes only the eligible selected documents, with the modal open, then clears the selection', async () => {
    const vec = fakeVec({ a: 'vectorized', b: 'pending' }, ['a', 'b', 'c'])
    const sel = useKnowledgeBrowserSelection(vec as never)
    await expect(sel.vectorizeSelected()).resolves.toBe(true)
    expect(vec.vectorizeBatch).toHaveBeenCalledWith(['b', 'c'])
    expect(vec.deselectAll).toHaveBeenCalledTimes(1)
    expect(sel.showProgressModal.value).toBe(true)
  })

  it('a selection of only vectorized documents submits nothing and opens no modal', async () => {
    const vec = fakeVec({ a: 'vectorized' }, ['a'])
    const sel = useKnowledgeBrowserSelection(vec as never)
    await expect(sel.vectorizeSelected()).resolves.toBe(true)
    expect(vec.vectorizeBatch).not.toHaveBeenCalled()
    expect(vec.deselectAll).toHaveBeenCalledTimes(1)
    expect(sel.showProgressModal.value).toBe(false)
  })

  it('reports a failed batch (false + onError) and still clears the busy flag', async () => {
    const vec = fakeVec({}, ['a'])
    vec.vectorizeBatch.mockRejectedValueOnce(new Error('boom'))
    const onError = vi.fn()
    const sel = useKnowledgeBrowserSelection(vec as never, onError)
    await expect(sel.vectorizeSelected()).resolves.toBe(false)
    expect(onError).toHaveBeenCalledTimes(1)
    expect(sel.isVectorizing.value).toBe(false)
  })

  it('a cancelled run settling late does not clear the busy flag of a newer run', async () => {
    const vec = fakeVec()
    let releaseFirst!: () => void
    vec.vectorizeDocument
      .mockImplementationOnce(() => new Promise((resolve) => { releaseFirst = () => resolve({}) }))
      .mockImplementationOnce(() => new Promise(() => {}))
    const sel = useKnowledgeBrowserSelection(vec as never)
    const first = sel.handleVectorizeDocument('a')
    sel.handleCancelVectorization()
    void sel.handleVectorizeDocument('b')
    expect(sel.isVectorizing.value).toBe(true)
    releaseFirst()
    await first
    expect(sel.isVectorizing.value).toBe(true)
  })

  it('reports a rejected retry through onError', async () => {
    const vec = fakeVec({ a: 'failed' })
    vec.vectorizeDocument.mockRejectedValueOnce(new Error('boom'))
    const onError = vi.fn()
    const sel = useKnowledgeBrowserSelection(vec as never, onError)
    await expect(sel.handleRetryFailed()).resolves.toBe(false)
    expect(onError).toHaveBeenCalledTimes(1)
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
