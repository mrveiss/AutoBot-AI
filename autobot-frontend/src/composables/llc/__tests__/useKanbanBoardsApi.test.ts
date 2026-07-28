// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * GH#12213: unit tests for the LLC boards API composable. Asserts each call
 * hits the right endpoint with the right payload and parses the response — the
 * create-kanban path in particular had no frontend caller before this.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'

const get = vi.fn()
const post = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get, post }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import { useKanbanBoardsApi } from '../useKanbanBoardsApi'

describe('useKanbanBoardsApi', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
  })

  it('listBoards() GETs /api/llc/boards and stores the parsed result', async () => {
    const rows = [
      { id: 'b1', company_id: 'c1', project_id: 'p1', sprint_id: null, type: 'kanban', name: 'K', created_at: '', updated_at: '' },
    ]
    get.mockResolvedValueOnce(rows)
    const { boards, listBoards } = useKanbanBoardsApi()

    const result = await listBoards()

    expect(get).toHaveBeenCalledWith('/api/llc/boards')
    expect(result).toEqual(rows)
    expect(boards.value).toEqual(rows)
  })

  it('listBoards() falls back to [] and captures error on failure', async () => {
    get.mockRejectedValueOnce(new Error('boom'))
    const { boards, error, listBoards } = useKanbanBoardsApi()

    await listBoards()

    expect(boards.value).toEqual([])
    expect(error.value).toBe('boom')
  })

  it('createKanbanBoard() POSTs to /api/llc/boards/kanban with the bound company_id', async () => {
    const board = { id: 'b2', type: 'kanban', name: 'New' }
    post.mockResolvedValueOnce(board)
    const { createKanbanBoard } = useKanbanBoardsApi()

    const result = await createKanbanBoard('c1', 'p9', 'My Board')

    expect(post).toHaveBeenCalledWith('/api/llc/boards/kanban', {
      company_id: 'c1',
      project_id: 'p9',
      name: 'My Board',
    })
    expect(result).toEqual(board)
  })

  it('createKanbanBoard() sends name: null when no name is given', async () => {
    post.mockResolvedValueOnce({ id: 'b3' })
    const { createKanbanBoard } = useKanbanBoardsApi()

    await createKanbanBoard('c1', 'p9')

    expect(post).toHaveBeenCalledWith('/api/llc/boards/kanban', {
      company_id: 'c1',
      project_id: 'p9',
      name: null,
    })
  })

  it('createSprintBoard() POSTs to /api/llc/boards/sprint with sprint_id', async () => {
    post.mockResolvedValueOnce({ id: 'b4', type: 'sprint' })
    const { createSprintBoard } = useKanbanBoardsApi()

    await createSprintBoard('c1', 's7')

    expect(post).toHaveBeenCalledWith('/api/llc/boards/sprint', {
      company_id: 'c1',
      sprint_id: 's7',
      name: null,
    })
  })

  it('moveItem() POSTs to /api/llc/boards/{id}/move with the move payload', async () => {
    const moved = { id: 'w1', identifier: 'WI-1', title: 'T', type: 'pbi', status: 'in_progress', priority: 'high' }
    post.mockResolvedValueOnce(moved)
    const { moveItem } = useKanbanBoardsApi()

    const result = await moveItem('b1', 'w1', 'col-2', 'actor-3')

    expect(post).toHaveBeenCalledWith('/api/llc/boards/b1/move', {
      work_item_id: 'w1',
      column_id: 'col-2',
      actor_id: 'actor-3',
    })
    expect(result).toEqual(moved)
  })
})
