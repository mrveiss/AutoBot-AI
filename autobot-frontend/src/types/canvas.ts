// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/** Streaming lifecycle state for an agent cell. */
export type CellStreamState = 'skeleton' | 'partial' | 'complete' | 'error'

/** Who owns a cell — determines visual treatment. */
export type CellOwner = 'agent' | 'user'

/** Cell type — phase 1 markdown only; chart/code show placeholder. */
export type CellContentType = 'markdown' | 'chart' | 'code'

export interface CanvasCell {
  id: string
  canvasId: string
  owner: CellOwner
  contentType: CellContentType
  content: string
  streamState: CellStreamState
  seq: number
  createdAt: string
  updatedAt: string
}

export interface CanvasDocument {
  id: string
  title: string
  cells: CanvasCell[]
  version: number
  updatedAt: string
}

/** WS message envelope from the backend. */
export interface CanvasWsMessage {
  type: 'canvas_cell'
  cellId: string
  seq: number
  delta: string
  state: CellStreamState
}

export type AutoSaveStatus = 'idle' | 'saving' | 'saved' | 'error'

export interface ConflictState {
  cellId: string
  pausedAgentSeq: number
}
