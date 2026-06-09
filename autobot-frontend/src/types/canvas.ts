// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/** Streaming lifecycle state for an agent cell. */
export type CellStreamState = 'skeleton' | 'partial' | 'complete' | 'error'

/** Who owns a cell — determines visual treatment. */
export type CellOwner = 'agent' | 'user'

/** Cell type — phase 1 markdown only; chart/code show placeholder. */
export type CellContentType = 'markdown' | 'chart' | 'code'

export interface ChartPayload {
  payloadType: 'vega-lite'
  specVersion: '5'
  spec: Record<string, unknown>
  executable?: boolean
}

export interface CodePayload {
  payloadType: 'code'
  code: string
  language?: string
  executable?: boolean
}

export type RichPayload = ChartPayload | CodePayload | null

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
  richPayload?: RichPayload
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
