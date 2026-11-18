// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useCanvasStore } from '@/stores/useCanvasStore'
import type { CanvasCell } from '@/types/canvas'

const mockCell = (): CanvasCell => ({
  id: 'cell-1', canvasId: 'canvas-1', owner: 'agent',
  contentType: 'markdown', content: '# Hello', streamState: 'complete',
  seq: 1, createdAt: '2026-01-01T00:00:00Z', updatedAt: '2026-01-01T00:00:00Z',
})

describe('useCanvasStore', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  describe('cell ids are unique regardless of the clock (#17020)', () => {
    // `addCell` minted `cell-${Date.now()}`. Two cells created inside the same
    // millisecond therefore shared an id, and every operation in this store
    // addresses a cell BY id. Frozen clock rather than a fast loop, because a
    // loop only reproduces it when the machine is quick enough -- which is why
    // this passed locally and failed in CI.
    beforeEach(() => { vi.useFakeTimers() })
    afterEach(() => { vi.useRealTimers() })

    it('gives two cells added in the same millisecond distinct ids', () => {
      const store = useCanvasStore()
      store.addCell('user')
      store.addCell('agent')

      const [first, second] = store.cells.slice(-2)
      expect(first.id).not.toBe(second.id)
    })

    it('keeps ids distinct across many cells in one tick', () => {
      const store = useCanvasStore()
      for (let i = 0; i < 25; i += 1) store.addCell('user')

      const ids = store.cells.map((cell) => cell.id)
      expect(new Set(ids).size).toBe(ids.length)
    })

    it('still addresses the right cell after a same-tick add', () => {
      // The consequence, not just the id: with a duplicate id, `deleteCell`
      // removed whichever cell `find` reached first rather than the one asked
      // for. Asserting the behaviour keeps this test meaningful if the id
      // scheme changes again.
      const store = useCanvasStore()
      store.addCell('user')
      store.addCell('agent')
      const target = store.cells[store.cells.length - 1].id
      const survivor = store.cells[store.cells.length - 2].id

      store.deleteCell(target)

      const remaining = store.cells.map((cell) => cell.id)
      expect(remaining).toContain(survivor)
      expect(remaining).not.toContain(target)
    })
  })

  it('starts empty', () => {
    const store = useCanvasStore()
    expect(store.cells).toEqual([])
    expect(store.canvasId).toBeNull()
  })

  it('setCanvas populates cells', () => {
    const store = useCanvasStore()
    store.setCanvas({ id: 'canvas-1', title: 'Test', cells: [mockCell()], version: 1, updatedAt: '' })
    expect(store.cells).toHaveLength(1)
    expect(store.canvasId).toBe('canvas-1')
  })

  it('upsertStreamCell creates new cell when not found', () => {
    const store = useCanvasStore()
    store.setCanvas({ id: 'c1', title: '', cells: [], version: 1, updatedAt: '' })
    store.upsertStreamCell({ cellId: 'c2', seq: 1, delta: 'hello ', state: 'partial' })
    store.upsertStreamCell({ cellId: 'c2', seq: 2, delta: 'world', state: 'partial' })
    const cell = store.cells.find(c => c.id === 'c2')
    expect(cell?.content).toBe('hello world')
    expect(cell?.streamState).toBe('partial')
  })

  it('upsertStreamCell with state=complete marks complete', () => {
    const store = useCanvasStore()
    store.setCanvas({ id: 'c1', title: '', cells: [], version: 1, updatedAt: '' })
    store.upsertStreamCell({ cellId: 'c2', seq: 1, delta: 'done', state: 'complete' })
    const cell = store.cells.find(c => c.id === 'c2')
    expect(cell?.streamState).toBe('complete')
  })

  it('undo/redo round-trips a cell edit', () => {
    const store = useCanvasStore()
    const cell = mockCell()
    store.setCanvas({ id: 'c1', title: '', cells: [cell], version: 1, updatedAt: '' })
    store.updateCellContent('cell-1', 'Modified')
    expect(store.cells[0].content).toBe('Modified')
    store.undo()
    expect(store.cells[0].content).toBe('# Hello')
    store.redo()
    expect(store.cells[0].content).toBe('Modified')
  })

  it('triggerConflict pauses streaming cell', () => {
    const store = useCanvasStore()
    store.setCanvas({ id: 'c1', title: '', cells: [], version: 1, updatedAt: '' })
    store.upsertStreamCell({ cellId: 'c2', seq: 1, delta: '...', state: 'partial' })
    store.triggerConflict('c2', 1)
    expect(store.conflict?.cellId).toBe('c2')
    expect(store.cells.find(c => c.id === 'c2')?.streamState).toBe('complete')
  })

  it('resolveConflict clears conflict state', () => {
    const store = useCanvasStore()
    store.setCanvas({ id: 'c1', title: '', cells: [], version: 1, updatedAt: '' })
    store.upsertStreamCell({ cellId: 'c2', seq: 1, delta: '...', state: 'partial' })
    store.triggerConflict('c2', 1)
    store.resolveConflict()
    expect(store.conflict).toBeNull()
  })

  it('deleteCell removes from list', () => {
    const store = useCanvasStore()
    store.setCanvas({ id: 'c1', title: '', cells: [mockCell()], version: 1, updatedAt: '' })
    store.deleteCell('cell-1')
    expect(store.cells).toHaveLength(0)
  })

  it('moveCell reorders cells', () => {
    const store = useCanvasStore()
    const a = { ...mockCell(), id: 'a', content: 'A' }
    const b = { ...mockCell(), id: 'b', content: 'B' }
    store.setCanvas({ id: 'c1', title: '', cells: [a, b], version: 1, updatedAt: '' })
    store.moveCell('a', 'down')
    expect(store.cells[0].id).toBe('b')
    expect(store.cells[1].id).toBe('a')
  })

  it('duplicateCell inserts copy after original', () => {
    const store = useCanvasStore()
    store.setCanvas({ id: 'c1', title: '', cells: [mockCell()], version: 1, updatedAt: '' })
    store.duplicateCell('cell-1')
    expect(store.cells).toHaveLength(2)
    expect(store.cells[1].id).not.toBe('cell-1')
    expect(store.cells[1].content).toBe('# Hello')
  })

  it('isEmpty returns true when no cells', () => {
    const store = useCanvasStore()
    store.setCanvas({ id: 'c1', title: '', cells: [], version: 1, updatedAt: '' })
    expect(store.isEmpty).toBe(true)
  })
})
