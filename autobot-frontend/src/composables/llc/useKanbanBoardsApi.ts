// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// GH#12213: shared client for the LLC boards API (llc/api/boards.py). The list,
// per-board and move endpoints were already consumed inline by BoardsView /
// KanbanBoardView / SprintBoardView, but the *create* endpoints
// (POST /kanban, POST /sprint) had no frontend caller, so a fresh company's
// empty board list was a dead end. This composable centralises four calls
// (list / create-kanban / create-sprint / move) so the create path is
// reachable and unit-testable.
//
// GH#13993: this comment previously advertised five calls including `items`,
// which was never implemented here — the board views call that endpoint
// directly. Corrected rather than left claiming a function that does not exist.
import { ref } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useKanbanBoardsApi')

export interface BoardSummary {
  id: string
  company_id: string
  project_id: string | null
  sprint_id: string | null
  type: 'kanban' | 'sprint'
  name: string
  created_at: string
  updated_at: string
}

export interface MovedItem {
  id: string
  identifier: string
  title: string
  type: string
  status: string
  priority: string
}

export function useKanbanBoardsApi() {
  const boards = ref<BoardSummary[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  /** List every board (kanban + sprint) for the caller's company. */
  async function listBoards(): Promise<BoardSummary[]> {
    isLoading.value = true
    error.value = null
    try {
      boards.value = (await useApiClient().get<BoardSummary[]>('/api/llc/boards')) ?? []
      return boards.value
    } catch (err: unknown) {
      error.value = (err instanceof Error && err.message) || 'Failed to load boards.'
      logger.error('Failed to load boards', err)
      boards.value = []
      return boards.value
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Get or create the kanban board for a project (idempotent server-side).
   * Binds company_id from the caller's scope; the backend rejects a mismatch.
   */
  async function createKanbanBoard(
    companyId: string,
    projectId: string,
    name?: string,
  ): Promise<BoardSummary> {
    return await useApiClient().post<BoardSummary>('/api/llc/boards/kanban', {
      company_id: companyId,
      project_id: projectId,
      name: name || null,
    })
  }

  /** Get or create the sprint board for a sprint (idempotent server-side). */
  async function createSprintBoard(
    companyId: string,
    sprintId: string,
    name?: string,
  ): Promise<BoardSummary> {
    return await useApiClient().post<BoardSummary>('/api/llc/boards/sprint', {
      company_id: companyId,
      sprint_id: sprintId,
      name: name || null,
    })
  }

  /** Move a work item to a column, enforcing WIP limits server-side. */
  async function moveItem(
    boardId: string,
    workItemId: string,
    columnId: string,
    actorId?: string,
  ): Promise<MovedItem> {
    return await useApiClient().post<MovedItem>(`/api/llc/boards/${boardId}/move`, {
      work_item_id: workItemId,
      column_id: columnId,
      actor_id: actorId || null,
    })
  }

  return {
    boards,
    isLoading,
    error,
    listBoards,
    createKanbanBoard,
    createSprintBoard,
    moveItem,
  }
}
