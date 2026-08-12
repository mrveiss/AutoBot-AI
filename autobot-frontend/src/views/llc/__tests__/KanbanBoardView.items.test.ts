// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// GH#13993: the board-items endpoint (GET /api/llc/boards/{id}/items) nests
// work items inside each column — there is no top-level `items` key. The
// view previously read `itemsData.items`, which is always undefined, so the
// board rendered zero cards in every column regardless of backend data.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
const post = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get, post }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { companyId: 'c1', boardId: 'b1' } }),
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('@/composables/useLiveEvents', () => ({
  useLiveEvents: () => ({ subscribe: vi.fn(() => vi.fn()) }),
}))

import KanbanBoardView from '../KanbanBoardView.vue'

interface WorkItemLike {
  id: string
  column_id?: string
  assignee_type?: string | null
}

interface KanbanVm {
  columns: { id: string; title: string; wip_limit: number | null }[]
  items: WorkItemLike[]
}

// Shape actually returned by GET /api/llc/boards/{id}/items — items nested
// per-column, each carrying `column_id` + `assignee_type` (backend/llc/api/boards.py).
const BOARD_ITEMS_RESPONSE = {
  board: { id: 'b1', name: 'Board' },
  columns: [
    {
      id: 'col-ready',
      name: 'Ready',
      position: 0,
      status_filter: ['ready'],
      wip_limit: null,
      items: [
        {
          id: 'wi-1',
          identifier: 'WI-1',
          title: 'First',
          type: 'task',
          status: 'ready',
          priority: 'medium',
          story_points: null,
          assignee_agent_id: null,
          assignee_user_id: 'u1',
          assignee_type: 'user',
          column_id: 'col-ready',
        },
      ],
      item_count: 1,
    },
    {
      id: 'col-progress',
      name: 'In Progress',
      position: 1,
      status_filter: ['in_progress'],
      wip_limit: null,
      items: [
        {
          id: 'wi-2',
          identifier: 'WI-2',
          title: 'Second',
          type: 'task',
          status: 'in_progress',
          priority: 'high',
          story_points: 3,
          assignee_agent_id: 'a1',
          assignee_user_id: null,
          assignee_type: 'agent',
          column_id: 'col-progress',
        },
      ],
      item_count: 1,
    },
  ],
}

// Shape actually returned by GET /api/llc/boards/{id} — see `_board_response`
// in autobot-backend/llc/api/boards.py. Columns carry `name` and
// `status_filter`; there is no `title` key. An earlier revision of this fixture
// claimed `title`, which is exactly the defect this file exists to catch.
const BOARD_RESPONSE = {
  id: 'b1',
  company_id: 'c1',
  project_id: null,
  sprint_id: null,
  type: 'kanban',
  name: 'Board',
  created_at: null,
  updated_at: null,
  columns: [
    { id: 'col-ready', name: 'Ready', position: 0, status_filter: ['ready'], wip_limit: null },
    { id: 'col-progress', name: 'In Progress', position: 1, status_filter: ['in_progress'], wip_limit: null },
  ],
}

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

async function mountView() {
  get.mockImplementation((url: string) => {
    if (url.endsWith('/items')) return Promise.resolve(BOARD_ITEMS_RESPONSE)
    return Promise.resolve(BOARD_RESPONSE)
  })
  const wrapper = mount(KanbanBoardView, {
    global: { plugins: [i18n], stubs: { WorkItemDetail: true } },
  })
  await flushPromises()
  return wrapper
}

describe('KanbanBoardView items wiring (GH#13993)', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
  })

  it('flattens columns[].items from the board-items response into items', async () => {
    const wrapper = await mountView()
    const vm = wrapper.vm as unknown as KanbanVm

    expect(vm.items.map(i => i.id).sort()).toEqual(['wi-1', 'wi-2'])
  })

  it('renders a card per item — the board is not empty when the backend has items', async () => {
    const wrapper = await mountView()

    expect(wrapper.findAll('.work-card')).toHaveLength(2)
    expect(wrapper.text()).toContain('First')
    expect(wrapper.text()).toContain('Second')
  })

  it('renders each column header from the `name` the board API actually sends', async () => {
    const wrapper = await mountView()

    // GH#13993: the view previously read `col.title`, a key `_board_response`
    // never emits, so every column header rendered blank.
    const headers = wrapper.findAll('.column-title').map(n => n.text())
    expect(headers).toEqual(['Ready', 'In Progress'])
  })

  it('assigns each item to its column via column_id from the response', async () => {
    const wrapper = await mountView()
    const vm = wrapper.vm as unknown as KanbanVm

    const wi1 = vm.items.find(i => i.id === 'wi-1')
    const wi2 = vm.items.find(i => i.id === 'wi-2')
    expect(wi1?.column_id).toBe('col-ready')
    expect(wi2?.column_id).toBe('col-progress')
  })

  it('swimlane split uses the backend vocabulary ("user"), not "human"', async () => {
    const wrapper = await mountView()
    // Enable swimlane grouping.
    await wrapper.find('.swimlane-toggle input').setValue(true)
    await flushPromises()

    // wi-1 (assignee_type "user") must land in the human swimlane and
    // wi-2 (assignee_type "agent") in the agent swimlane. Each column has
    // exactly one of the two types, so each column shows exactly one
    // populated lane and one empty lane — never both empty, which is what
    // happened while the filter compared against the literal "human".
    expect(wrapper.findAll('.work-card')).toHaveLength(2)
    expect(wrapper.findAll('.lane-empty')).toHaveLength(2)
  })
})
