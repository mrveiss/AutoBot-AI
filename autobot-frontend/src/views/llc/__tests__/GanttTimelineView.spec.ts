// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
// #11701 — GanttTimelineView scopes to the originating sprint board's work
// items when opened with a `board` query param; otherwise renders the
// company-wide roadmap unchanged.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

// --- module mocks ---------------------------------------------------------
const h = vi.hoisted(() => ({
  route: { params: {} as Record<string, string>, query: {} as Record<string, string> },
  router: { replace: vi.fn() },
  api: { get: vi.fn(), patch: vi.fn() },
}))

vi.mock('vue-router', () => ({
  useRoute: () => h.route,
  useRouter: () => h.router,
}))
vi.mock('@/plugins/api', () => ({ useApiClient: () => h.api }))
vi.mock('@/composables/useNotificationBus', () => ({
  useNotificationBus: () => ({ showToast: vi.fn() }),
}))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import GanttTimelineView from '../GanttTimelineView.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

function timelineItem(id: string, identifier: string) {
  return {
    id,
    identifier,
    title: `Item ${identifier}`,
    type: 'task',
    status: 'todo',
    scheduled_start: '2026-01-01T00:00:00Z',
    scheduled_end: '2026-01-05T00:00:00Z',
    started_at: null,
    completed_at: null,
    on_critical_path: false,
  }
}

// project p1 has three items; the sprint board b1 only contains w1 + w2.
const PROJECT_TIMELINE = {
  project_id: 'p1',
  items: [timelineItem('w1', 'WI-1'), timelineItem('w2', 'WI-2'), timelineItem('w3', 'WI-3')],
  edges: [{ from_id: 'w1', to_id: 'w3' }],
}

function wireApi() {
  h.api.get.mockImplementation((url: string) => {
    if (url === '/api/llc/boards/b1') return Promise.resolve({ project_id: 'p1', name: 'Sprint 3 Board' })
    if (url === '/api/llc/boards/b1/items') return Promise.resolve({ items: [{ id: 'w1' }, { id: 'w2' }] })
    if (url === '/api/llc/companies/c1/projects')
      return Promise.resolve([{ id: 'p1', name: 'Proj 1' }, { id: 'p2', name: 'Proj 2' }])
    if (url === '/api/llc/projects/p1/timeline') return Promise.resolve(PROJECT_TIMELINE)
    return Promise.reject(new Error(`unexpected url ${url}`))
  })
}

function mountView() {
  return mount(GanttTimelineView, { global: { plugins: [i18n] } })
}

describe('GanttTimelineView board/sprint scope (#11701)', () => {
  beforeEach(() => {
    h.route.params = { companyId: 'c1' }
    h.route.query = {}
    h.router.replace.mockReset()
    wireApi()
  })

  it('scopes the timeline to the sprint board when opened with a board query', async () => {
    h.route.query = { board: 'b1' }
    const w = mountView()
    await flushPromises()

    // Board metadata + membership were fetched to resolve the scope.
    expect(h.api.get).toHaveBeenCalledWith('/api/llc/boards/b1')
    expect(h.api.get).toHaveBeenCalledWith('/api/llc/boards/b1/items')
    // The board's project drove the timeline request.
    expect(h.api.get).toHaveBeenCalledWith('/api/llc/projects/p1/timeline')

    // Only the two board members render — w3 is filtered out.
    const rows = w.findAll('.gantt-row')
    expect(rows).toHaveLength(2)
    const labels = w.findAll('.gantt-row-label').map((n) => n.text())
    expect(labels).toEqual(['WI-1', 'WI-2'])

    // The scope banner is visible and the project selector is hidden.
    expect(w.find('.gantt-scope').exists()).toBe(true)
    expect(w.text()).toContain('Sprint 3 Board')
    expect(w.find('select').exists()).toBe(true) // zoom select still present
    expect(w.findAll('.gantt-field')).toHaveLength(1) // project field hidden, only zoom
  })

  it('renders the whole company timeline (no scope) when no board query is present', async () => {
    const w = mountView()
    await flushPromises()

    expect(h.api.get).not.toHaveBeenCalledWith('/api/llc/boards/b1')
    const rows = w.findAll('.gantt-row')
    expect(rows).toHaveLength(3)
    expect(w.find('.gantt-scope').exists()).toBe(false)
    // project selector present in the global view.
    expect(w.findAll('.gantt-field')).toHaveLength(2)
  })

  it('clears the scope and returns to the company-wide roadmap', async () => {
    h.route.query = { board: 'b1' }
    const w = mountView()
    await flushPromises()
    expect(w.findAll('.gantt-row')).toHaveLength(2)

    await w.find('.gantt-scope-clear').trigger('click')
    await flushPromises()

    expect(h.router.replace).toHaveBeenCalledWith({ name: 'llc-timeline', params: { companyId: 'c1' } })
    // filter dropped — all three items now render.
    expect(w.findAll('.gantt-row')).toHaveLength(3)
    expect(w.find('.gantt-scope').exists()).toBe(false)
  })
})
