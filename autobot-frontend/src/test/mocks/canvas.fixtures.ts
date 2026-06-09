// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// Typed fixture factories for Live Canvas API — MVA-399
// Shapes match the frozen contract at MVA-359#document-api-contract

export type CellType = 'text' | 'code' | 'chart' | 'image'
export type CellState =
  | 'queued'
  | 'skeleton'
  | 'streaming'
  | 'complete'
  | 'committed'
  | 'error'
  | 'cancelled'
export type CellOwner = 'agent' | 'user'
export type ExportFormat = 'md' | 'json' | 'html' | 'pdf'
export type UndoEventType =
  | 'cell_add'
  | 'cell_edit'
  | 'cell_delete'
  | 'cell_accept'
  | 'cell_discard'
export type CellAction = 'accept' | 'edit' | 'discard'

export interface CanvasFixture {
  id: string
  user_id: string
  title: string
  created_at: string
  updated_at: string
  save_token: string
  undo_cursor: number
}

export interface CanvasCellFixture {
  id: string
  canvas_id: string
  user_id: string
  position: number
  type: CellType
  content: string
  state: CellState
  owner: CellOwner
  version: number
  locked_by: string | null
  created_at: string
  updated_at: string
}

export interface CanvasUndoEventFixture {
  id: string
  canvas_id: string
  seq: number
  event_type: UndoEventType
  payload: Record<string, unknown>
  created_at: string
}

export interface CanvasGetResponse {
  canvas: Omit<CanvasFixture, 'user_id'>
  cells: Omit<CanvasCellFixture, 'canvas_id' | 'user_id' | 'created_at' | 'updated_at'>[]
}

export interface CanvasAutosaveResponse {
  save_token: string
  saved_at: string
}

export interface CanvasCellTransitionResponse {
  id: string
  state: CellState
  version: number
  content: string
  updated_at: string
}

export interface CanvasWsEnvelope {
  type: 'canvas_cell'
  cellId: string
  seq: number
  delta: string | null
  state: CellState
}

export interface CanvasCancelMessage {
  type: 'canvas_cancel'
  cellId: string
}

let _seq = 0
const iso = () => new Date().toISOString()
const uuid = () => crypto.randomUUID()

export const makeCanvas = (overrides: Partial<CanvasFixture> = {}): CanvasFixture => ({
  id: uuid(),
  user_id: 'user-test-001',
  title: 'Test Canvas',
  created_at: iso(),
  updated_at: iso(),
  save_token: uuid(),
  undo_cursor: 0,
  ...overrides,
})

export const makeCanvasCell = (
  overrides: Partial<CanvasCellFixture> = {},
): CanvasCellFixture => ({
  id: uuid(),
  canvas_id: 'canvas-test-001',
  user_id: 'user-test-001',
  position: 0,
  type: 'text',
  content: 'Test cell content',
  state: 'committed',
  owner: 'user',
  version: 1,
  locked_by: null,
  created_at: iso(),
  updated_at: iso(),
  ...overrides,
})

export const makeAgentCell = (overrides: Partial<CanvasCellFixture> = {}): CanvasCellFixture =>
  makeCanvasCell({
    owner: 'agent',
    state: 'complete',
    content: 'Agent-generated content awaiting review',
    ...overrides,
  })

export const makeCanvasGetResponse = (
  canvas?: Partial<CanvasFixture>,
  cells?: Partial<CanvasCellFixture>[],
): CanvasGetResponse => {
  const c = makeCanvas(canvas)
  return {
    canvas: {
      id: c.id,
      title: c.title,
      created_at: c.created_at,
      updated_at: c.updated_at,
      save_token: c.save_token,
      undo_cursor: c.undo_cursor,
    },
    cells: (cells ?? [{}]).map((overrides, i) => {
      const cell = makeCanvasCell({ canvas_id: c.id, position: i, ...overrides })
      return {
        id: cell.id,
        position: cell.position,
        type: cell.type,
        content: cell.content,
        state: cell.state,
        owner: cell.owner,
        version: cell.version,
        locked_by: cell.locked_by,
      }
    }),
  }
}

export const makeAutosaveResponse = (): CanvasAutosaveResponse => ({
  save_token: uuid(),
  saved_at: iso(),
})

export const makeWsEnvelope = (
  cellId: string,
  overrides: Partial<Omit<CanvasWsEnvelope, 'type' | 'cellId'>> = {},
): CanvasWsEnvelope => ({
  type: 'canvas_cell',
  cellId,
  seq: ++_seq,
  delta: 'streaming chunk',
  state: 'streaming',
  ...overrides,
})

export const resetFixtureSeq = () => {
  _seq = 0
}
