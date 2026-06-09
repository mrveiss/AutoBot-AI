// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { http, HttpResponse } from 'msw'
import type { CanvasDocument } from '@/types/canvas'

const MOCK_CANVAS: CanvasDocument = {
  id: 'canvas-test-1',
  title: 'Test Canvas',
  cells: [
    {
      id: 'cell-1', canvasId: 'canvas-test-1', owner: 'user',
      contentType: 'markdown', content: '# Welcome\nThis is a test canvas.',
      streamState: 'complete', seq: 1,
      createdAt: '2026-01-01T00:00:00Z', updatedAt: '2026-01-01T00:00:00Z',
    },
  ],
  version: 1,
  updatedAt: '2026-01-01T00:00:00Z',
}

export const canvasHandlers = [
  http.get('/api/canvas/:id', ({ params }) => {
    return HttpResponse.json({ ...MOCK_CANVAS, id: params.id as string })
  }),

  http.put('/api/canvas/:id', async ({ request }) => {
    const body = await request.json() as { cells: unknown[] }
    return HttpResponse.json({ ...MOCK_CANVAS, cells: body.cells, version: 2 })
  }),

  http.post('/api/canvas/:id/cells', async ({ params, request }) => {
    const body = await request.json() as Record<string, unknown>
    return HttpResponse.json({
      ...body,
      id: `cell-${Date.now()}`,
      canvasId: params.id as string,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    })
  }),

  http.patch('/api/canvas/:id/cells/:cellId', async ({ request }) => {
    const body = await request.json() as Record<string, unknown>
    return HttpResponse.json({ id: 'cell-patched', ...body, updatedAt: new Date().toISOString() })
  }),

  http.post('/api/canvas/:id/export', async ({ request }) => {
    const body = await request.json() as { format: string }
    return HttpResponse.json({ url: `/exports/canvas-test.${body.format}`, format: body.format })
  }),
]
