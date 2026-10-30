// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// The comments tab is back (#18750): GET /api/llc/work-items/{id}/comments is served, so opening
// the tab lists what fetchComments returns ({ comments: [...] }).

import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { defineComponent, h } from 'vue'
import en from '@/i18n/locales/en.json'

const get = vi.fn(async (url: string) =>
  url.endsWith('/comments')
    ? { comments: [{ id: 'c1', work_item_id: 'w1', body: 'first note', author_user_id: 'u1', created_at: '2026-01-01T00:00:00+00:00' }] }
    : [],
)
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

describe('WorkItemDetail comments tab', () => {
  it('shows the tab and lists the comments the route returns', async () => {
    const w = mount(WorkItemDetail, {
      props: { item: { ...ITEM }, companyId: 'c1' },
      global: { plugins: [i18n], stubs: { Teleport: true, WorkItemBadge: Stub, HandoffModal: Stub } },
      attachTo: document.body,
    })
    await flushPromises()
    const tab = w.findAll('.tab-btn').find((b) => b.text() === en.llc.workItem.tabComments)
    expect(tab).toBeTruthy()
    await tab!.trigger('click')
    await flushPromises()
    expect(get).toHaveBeenCalledWith('/api/llc/work-items/w1/comments')
    expect(w.findAll('.comment-item')).toHaveLength(1)
    expect(w.find('.comment-body').text()).toContain('first note')
    w.unmount()
  })
})
