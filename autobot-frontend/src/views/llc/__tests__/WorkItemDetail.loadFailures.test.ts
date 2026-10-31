// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// #20068: a failed load of any side panel says so through an i18n key instead of rendering the
// empty state, and comments page on the route's has_more instead of stopping at the first page.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { defineComponent, h } from 'vue'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get, post: vi.fn(), patch: vi.fn() }) }))
vi.mock('@/utils/debugUtils', () => ({ createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }) }))
vi.mock('@/composables/llc/useCompanyPeople', () => ({
  useCompanyPeople: () => ({ agents: { value: [] }, humans: { value: [] }, isLoading: { value: false }, load: vi.fn() }),
}))

import WorkItemDetail from '../WorkItemDetail.vue'

const ITEM = {
  id: 'w1', identifier: 'ACME-42', title: 'Ship it', description: '', type: 'task', status: 'todo',
  priority: 'medium', acceptance_criteria: [], acceptance_criteria_done: [],
}
const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', missingWarn: false, messages: { en } })
const Stub = defineComponent({ setup: () => () => h('span') })
const E = en.llc.workItem

async function openTab(label: string) {
  const w = mount(WorkItemDetail, {
    props: { item: { ...ITEM }, companyId: 'c1' },
    global: { plugins: [i18n], stubs: { Teleport: true, WorkItemBadge: Stub, HandoffModal: Stub } },
    attachTo: document.body,
  })
  await flushPromises()
  await w.findAll('.tab-btn').find((b) => b.text() === label)!.trigger('click')
  await flushPromises()
  return w
}

const comment = (id: string) => ({ id, work_item_id: 'w1', body: `note ${id}`, author_user_id: 'u1', created_at: '2026-01-01T00:00:00+00:00' })

beforeEach(() => get.mockReset())

describe('failed side-panel loads are not the empty state', () => {
  it.each([
    ['comments', E.tabComments, E.noComments, E.errors.commentsFailed],
    ['artifacts', E.tabArtifacts, E.noArtifacts, E.errors.artifactsFailed],
    ['activity', E.tabActivity, E.noActivity, E.errors.activityFailed],
    ['handoff', E.tabHandoff, E.noHandoffBrief, E.errors.handoffFailed],
  ])('%s tab shows the failure and not the empty text', async (_name, tab, empty, failure) => {
    get.mockImplementation(async (url?: string) => {
      if (/\/(comments|products|activity|handoff-brief)$/.test(String(url))) throw new Error('HTTP 500')
      return []
    })
    const w = await openTab(tab)
    const alert = w.find('[role="alert"]')
    expect(alert.exists()).toBe(true)
    expect(alert.text()).toBe(failure)
    expect(w.text()).not.toContain(empty)
    w.unmount()
  })
})

describe('comments paging', () => {
  it('offers more when the route says more exist and appends the next page', async () => {
    get.mockImplementation(async (url?: string) =>
      String(url).includes('offset=1') ? { comments: [comment('c2')], has_more: false } : { comments: [comment('c1')], has_more: true },
    )
    const w = await openTab(E.tabComments)
    expect(w.findAll('.comment-item')).toHaveLength(1)
    const more = w.findAll('button').find((b) => b.text() === E.loadMoreComments)
    expect(more).toBeTruthy()
    await more!.trigger('click')
    await flushPromises()
    expect(get).toHaveBeenCalledWith('/api/llc/work-items/w1/comments?offset=1')
    expect(w.findAll('.comment-item')).toHaveLength(2)
    expect(w.findAll('button').some((b) => b.text() === E.loadMoreComments)).toBe(false)
    w.unmount()
  })

  it('offers nothing more when the route says the page was the last', async () => {
    get.mockResolvedValue({ comments: [comment('c1')], has_more: false })
    const w = await openTab(E.tabComments)
    expect(w.findAll('button').some((b) => b.text() === E.loadMoreComments)).toBe(false)
    w.unmount()
  })
})
