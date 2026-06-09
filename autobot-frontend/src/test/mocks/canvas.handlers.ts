// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// MSW handlers for Live Canvas API — MVA-399
// Frozen contract: MVA-359#document-api-contract
// All 5 REST endpoints + error variants

import { http, HttpResponse } from 'msw'
import { ServiceURLs } from '@/constants/network'
import {
  makeCanvasGetResponse,
  makeCanvasCell,
  makeAutosaveResponse,
  type CellAction,
  type CellState,
  type ExportFormat,
} from './canvas.fixtures'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ServiceURLs.BACKEND_LOCAL

// State-machine: which target state results from each action
const TRANSITION_MAP: Record<CellAction, CellState> = {
  accept: 'committed',
  edit: 'committed',
  discard: 'cancelled',
}

// States that allow accept/edit/discard (agent cells must be complete first)
const _TRANSITIONABLE_STATES: CellState[] = ['complete', 'committed']

export const canvasHandlers = [
  // GET /api/canvas/{id}
  http.get(`${API_BASE}/api/canvas/:id`, ({ params }) => {
    const id = params.id as string
    const agentCell = makeCanvasCell({
      canvas_id: id,
      owner: 'agent',
      state: 'complete',
      content: 'Agent draft awaiting review',
      position: 1,
    })
    const userCell = makeCanvasCell({
      canvas_id: id,
      owner: 'user',
      state: 'committed',
      content: 'User cell',
      position: 0,
    })
    const response = makeCanvasGetResponse({ id }, [
      { ...userCell },
      { ...agentCell },
    ])
    return HttpResponse.json(response)
  }),

  // PUT /api/canvas/{id} — autosave
  http.put(`${API_BASE}/api/canvas/:id`, async ({ request }) => {
    await request.json() // consume body; optimistic — ignore content in mock
    return HttpResponse.json(makeAutosaveResponse())
  }),

  // POST /api/canvas/{id}/cells — add user-owned cell
  http.post(`${API_BASE}/api/canvas/:id/cells`, async ({ request, params }) => {
    const body = await request.json() as { type?: string; content?: string; position?: number }
    const cell = makeCanvasCell({
      canvas_id: params.id as string,
      owner: 'user',
      state: 'committed',
      type: (body.type as 'text' | 'code' | 'chart' | 'image') ?? 'text',
      content: body.content ?? '',
      position: body.position ?? 0,
    })
    return HttpResponse.json(
      {
        id: cell.id,
        canvas_id: cell.canvas_id,
        position: cell.position,
        type: cell.type,
        content: cell.content,
        state: cell.state,
        owner: cell.owner,
        version: cell.version,
        locked_by: cell.locked_by,
        created_at: cell.created_at,
      },
      { status: 201 },
    )
  }),

  // PATCH /api/canvas/{id}/cells/{cellId} — accept | edit | discard
  http.patch(`${API_BASE}/api/canvas/:id/cells/:cellId`, async ({ request, params }) => {
    const body = await request.json() as { action: CellAction; content?: string }
    const { action, content } = body

    const targetState = TRANSITION_MAP[action]
    if (!targetState) {
      return HttpResponse.json(
        { detail: 'Cell not in a state that allows this action' },
        { status: 409 },
      )
    }

    return HttpResponse.json({
      id: params.cellId as string,
      state: targetState,
      version: 2,
      content: action === 'edit' ? (content ?? '') : 'Agent draft awaiting review',
      updated_at: new Date().toISOString(),
    })
  }),

  // POST /api/canvas/{id}/export
  http.post(`${API_BASE}/api/canvas/:id/export`, async ({ request }) => {
    const body = await request.json() as { format: ExportFormat; include?: Record<string, boolean> }
    const format = body.format ?? 'md'

    const contentTypeMap: Record<ExportFormat, string> = {
      md: 'text/markdown; charset=utf-8',
      json: 'application/json',
      html: 'text/html; charset=utf-8',
      pdf: 'application/pdf',
    }

    const mockExportBody: Record<ExportFormat, string> = {
      md: '# Canvas Export\n\nMock markdown export.',
      json: JSON.stringify({ canvas: 'mock', cells: [] }),
      html: '<!DOCTYPE html><html><body><h1>Canvas Export</h1></body></html>',
      pdf: '%PDF-1.4 mock',
    }

    return new HttpResponse(mockExportBody[format], {
      status: 200,
      headers: { 'Content-Type': contentTypeMap[format] },
    })
  }),
]

// Error scenario handlers for canvas endpoints
export const canvasErrorHandlers = [
  http.get(`${API_BASE}/api/canvas/:id`, () =>
    HttpResponse.json({ detail: 'Forbidden' }, { status: 403 }),
  ),

  http.put(`${API_BASE}/api/canvas/:id`, () =>
    HttpResponse.json({ detail: 'Forbidden' }, { status: 403 }),
  ),

  http.post(`${API_BASE}/api/canvas/:id/cells`, () =>
    HttpResponse.json({ detail: 'Forbidden' }, { status: 403 }),
  ),

  http.patch(`${API_BASE}/api/canvas/:id/cells/:cellId`, () =>
    HttpResponse.json({ detail: 'Cell not in a state that allows this action' }, { status: 409 }),
  ),

  http.post(`${API_BASE}/api/canvas/:id/export`, () =>
    HttpResponse.json({ detail: 'Internal server error' }, { status: 500 }),
  ),
]

// Handler that returns 404 for a canvas that doesn't exist
export const canvasNotFoundHandlers = [
  http.get(`${API_BASE}/api/canvas/:id`, () =>
    HttpResponse.json({ detail: 'Canvas not found' }, { status: 404 }),
  ),
]

// Simulate cell state in transition conflict (409) on PATCH
export const canvasInvalidTransitionHandlers = [
  http.patch(`${API_BASE}/api/canvas/:id/cells/:cellId`, () =>
    HttpResponse.json(
      { detail: 'Cell not in a state that allows this action' },
      { status: 409 },
    ),
  ),
]
