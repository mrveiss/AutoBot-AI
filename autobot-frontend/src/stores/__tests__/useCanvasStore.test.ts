// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
import { describe, it, expect, beforeEach } from 'vitest'
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
