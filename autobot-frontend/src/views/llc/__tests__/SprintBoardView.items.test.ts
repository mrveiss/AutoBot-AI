// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// GH#13993: the board-items endpoint (GET /api/llc/boards/{id}/items) nests
// work items inside each column — there is no top-level `items` key.
// SprintBoardView shares the same bug as KanbanBoardView: it read
// `sprintData.items`, which is always undefined, so the sprint board
// rendered zero cards regardless of backend data.

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

import SprintBoardView from '../SprintBoardView.vue'

interface WorkItemLike {
  id: string
  column_id?: string
}

interface SprintVm {
  items: WorkItemLike[]
}

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
  ],
}

// Shape actually returned by GET /api/llc/boards/{id} — see `_board_response`
// in autobot-backend/llc/api/boards.py. Columns carry `name`/`status_filter`,
// and the response has NO `sprint` and NO `burndown` key.
//
// An earlier revision of this fixture invented all three. That fiction hid two
// live defects, now filed as GH#14074: SprintBoardView reads `boardData.sprint`
// and `boardData.burndown`, so the sprint header never renders and the burndown
// is permanently the empty state. The assertions below pin that real behaviour
// rather than a shape the API does not send; they flip when GH#14074 is fixed.
const BOARD_RESPONSE = {
  id: 'b1',
  company_id: 'c1',
  project_id: null,
  sprint_id: 's1',
  type: 'sprint',
  name: 'Board',
  created_at: null,
  updated_at: null,
  columns: [{ id: 'col-ready', name: 'Ready', position: 0, status_filter: ['ready'], wip_limit: null }],
}

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

// GH#14074: the view now fetches the sprint and its burndown from the endpoints
// that actually serve them, keyed off the board's `sprint_id`. Shapes copied
// from the backend rather than invented — `sprint_planning.get_burndown`
// returns `series` (not `points`), and each entry is
// `{"date": <iso string>, "remaining": <int>}` (not `{ day: number }`).
const SPRINT_RESPONSE = {
  id: 's1',
  name: 'Sprint 1',
  status: 'active',
  start_date: '2026-09-01',
  end_date: '2026-09-14',
}

const BURNDOWN_RESPONSE = {
  sprint_id: 's1',
  sprint_name: 'Sprint 1',
  total_points: 8,
  series: [
    { date: '2026-09-01T00:00:00', remaining: 8 },
    { date: '2026-09-02T00:00:00', remaining: 5 },
  ],
}

async function mountView() {
  get.mockImplementation((url: string) => {
    if (url.endsWith('/items')) return Promise.resolve(BOARD_ITEMS_RESPONSE)
    if (url.endsWith('/burndown')) return Promise.resolve(BURNDOWN_RESPONSE)
    if (url.includes('/sprints/')) return Promise.resolve(SPRINT_RESPONSE)
    return Promise.resolve(BOARD_RESPONSE)
  })
  const wrapper = mount(SprintBoardView, {
    global: { plugins: [i18n], stubs: { WorkItemDetail: true } },
  })
  await flushPromises()
  return wrapper
}

describe('SprintBoardView items wiring (GH#13993)', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
  })

  it('flattens columns[].items from the board-items response into items', async () => {
    const wrapper = await mountView()
    const vm = wrapper.vm as unknown as SprintVm

    expect(vm.items.map(i => i.id)).toEqual(['wi-1'])
  })

  it('renders a card — the sprint board is not empty when the backend has items', async () => {
    const wrapper = await mountView()

    expect(wrapper.findAll('.work-card')).toHaveLength(1)
    expect(wrapper.text()).toContain('First')
  })

  it('renders the column header from the `name` the board API actually sends', async () => {
    const wrapper = await mountView()

    // GH#13993: the view previously read `col.title`, a key `_board_response`
    // never emits, so every column header rendered blank.
    expect(wrapper.findAll('.column-title').map(n => n.text())).toEqual(['Ready'])
  })

  it('GH#14074: the sprint header and burndown render from their own endpoints', async () => {
    const wrapper = await mountView()

    // Flipped from the documented failing behaviour. The view used to read
    // `sprint` and `burndown` off GET /api/llc/boards/{id}, which has never
    // carried either, so both reads fell to their null/[] branch and these
    // panels were permanently empty. They now come from the endpoints that
    // serve them.
    expect(wrapper.find('.sprint-title').exists()).toBe(true)
    expect(wrapper.find('.burndown-chart').exists()).toBe(true)
    expect(wrapper.find('.chart-empty').exists()).toBe(false)
  })

  it('GH#14074: asks the sprint endpoints for the board\'s sprint_id', async () => {
    await mountView()

    const urls = get.mock.calls.map((call: unknown[]) => String(call[0]))
    expect(urls).toContain('/api/llc/sprints/s1')
    expect(urls).toContain('/api/llc/sprints/s1/burndown')
  })

  it('GH#14074: a board with no sprint_id asks for neither', async () => {
    get.mockImplementation((url: string) => {
      if (url.endsWith('/items')) return Promise.resolve(BOARD_ITEMS_RESPONSE)
      return Promise.resolve({ ...BOARD_RESPONSE, sprint_id: null })
    })
    const wrapper = mount(SprintBoardView, {
      global: { plugins: [i18n], stubs: { WorkItemDetail: true } },
    })
    await flushPromises()

    const urls = get.mock.calls.map((call: unknown[]) => String(call[0]))
    expect(urls.some(u => u.includes('/sprints/'))).toBe(false)
    expect(wrapper.find('.chart-empty').exists()).toBe(true)
  })
})
