// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { CanvasCell, CanvasDocument, ConflictState, CanvasWsMessage } from '@/types/canvas'

type HistoryEntry = { cells: CanvasCell[] }

export const useCanvasStore = defineStore('canvas', () => {
  const canvasId = ref<string | null>(null)
  const cells = ref<CanvasCell[]>([])
  const conflict = ref<ConflictState | null>(null)
  const isDirty = ref(false)
  const focusedCellId = ref<string | null>(null)

  const _history: HistoryEntry[] = []
  let _historyIndex = -1

  function _snapshot() {
    // Drop any forward (redo) states, then push post-edit state
    _history.splice(_historyIndex + 1)
    _history.push({ cells: cells.value.map(c => ({ ...c })) })
    _historyIndex = _history.length - 1
    if (_history.length > 100) { _history.shift(); _historyIndex-- }
  }

  function setCanvas(doc: CanvasDocument) {
    canvasId.value = doc.id
    cells.value = doc.cells.map(c => ({ ...c }))
    // Seed history with initial state so undo can return to it
    _history.length = 0
    _history.push({ cells: cells.value.map(c => ({ ...c })) })
    _historyIndex = 0
    isDirty.value = false
  }

  function upsertStreamCell(msg: Pick<CanvasWsMessage, 'cellId' | 'seq' | 'delta' | 'state'>) {
    const existing = cells.value.find(c => c.id === msg.cellId)
    if (existing) {
      existing.content += msg.delta
      existing.streamState = msg.state
      existing.seq = msg.seq
    } else {
      cells.value.push({
        id: msg.cellId,
        canvasId: canvasId.value ?? '',
        owner: 'agent',
        contentType: 'markdown',
        content: msg.delta,
        streamState: msg.state,
        seq: msg.seq,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      })
    }
    isDirty.value = true
  }

  function updateCellContent(cellId: string, content: string) {
    const cell = cells.value.find(c => c.id === cellId)
    if (cell) {
      cell.content = content
      cell.updatedAt = new Date().toISOString()
      isDirty.value = true
      _snapshot()
    }
  }

  function deleteCell(cellId: string) {
    cells.value = cells.value.filter(c => c.id !== cellId)
    isDirty.value = true
    _snapshot()
  }

  function moveCell(cellId: string, direction: 'up' | 'down') {
    const idx = cells.value.findIndex(c => c.id === cellId)
    if (idx < 0) return
    const target = direction === 'up' ? idx - 1 : idx + 1
    if (target < 0 || target >= cells.value.length) return
    const tmp = cells.value[idx]
    cells.value[idx] = cells.value[target]
    cells.value[target] = tmp
    isDirty.value = true
    _snapshot()
  }

  function duplicateCell(cellId: string) {
    const idx = cells.value.findIndex(c => c.id === cellId)
    if (idx < 0) return
    const clone: CanvasCell = {
      ...cells.value[idx],
      id: `${cellId}-copy-${Date.now()}`,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    }
    cells.value.splice(idx + 1, 0, clone)
    isDirty.value = true
    _snapshot()
  }

  function addCell(owner: 'user' | 'agent' = 'user') {
    cells.value.push({
      id: `cell-${Date.now()}`,
      canvasId: canvasId.value ?? '',
      owner,
      contentType: 'markdown',
      content: '',
      streamState: 'complete',
      seq: cells.value.length,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    })
    isDirty.value = true
    _snapshot()
  }

  function triggerConflict(cellId: string, pausedAgentSeq: number) {
    const cell = cells.value.find(c => c.id === cellId)
    if (cell) cell.streamState = 'complete'
    conflict.value = { cellId, pausedAgentSeq }
  }

  function resolveConflict() {
    conflict.value = null
  }

  function undo() {
    if (_historyIndex <= 0) return
    _historyIndex--
    cells.value = _history[_historyIndex].cells.map(c => ({ ...c }))
    isDirty.value = true
  }

  function redo() {
    if (_historyIndex >= _history.length - 1) return
    _historyIndex++
    cells.value = _history[_historyIndex].cells.map(c => ({ ...c }))
    isDirty.value = true
  }

  function markSaved() {
    isDirty.value = false
  }

  function setFocusedCell(cellId: string | null) {
    focusedCellId.value = cellId
  }

  const canUndo = computed(() => _historyIndex > 0)
  const canRedo = computed(() => _historyIndex < _history.length - 1)
  const isEmpty = computed(() => cells.value.length === 0)

  return {
    canvasId, cells, conflict, isDirty, focusedCellId,
    canUndo, canRedo, isEmpty,
    setCanvas, upsertStreamCell, updateCellContent,
    deleteCell, moveCell, duplicateCell, addCell,
    triggerConflict, resolveConflict, undo, redo, markSaved,
    setFocusedCell,
  }
})
