// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// GH#10040: BacklogView now wires drag-reorder + suggest-AC to the #9861
// backends. These tests assert the endpoints + payloads and the revert-on-error
// behaviour for reorder.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const post = vi.fn()
const get = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get, post }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { companyId: 'c1' } }),
  useRouter: () => ({ push: vi.fn() }),
}))

import BacklogView from '../BacklogView.vue'

interface WorkItemLike {
  id: string
}

// Surface of the <script setup> bindings the tests drive.
interface BacklogVm {
  items: WorkItemLike[]
  newItem: { title: string; description: string }
  suggestedACs: { text: string; selected: boolean }[]
  onDragStart: (item: WorkItemLike) => void
  onDrop: (target: WorkItemLike) => Promise<void>
  suggestAC: () => Promise<void>
}

const ITEMS = [
  { id: 'a', title: 'A', type: 'pbi', status: 'new', priority: 'medium', backlog_position: 0 },
  { id: 'b', title: 'B', type: 'pbi', status: 'new', priority: 'medium', backlog_position: 1 },
  { id: 'c', title: 'C', type: 'pbi', status: 'new', priority: 'medium', backlog_position: 2 },
]

// vue-i18n 11 requires app.use(); install a real i18n plugin (BacklogView uses
// useI18n()) so mounting doesn't throw. Real en.json keeps template render valid.
const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

async function mountView() {
  get.mockResolvedValue({ items: ITEMS.map(i => ({ ...i })) })
  const wrapper = mount(BacklogView, {
    global: { plugins: [i18n], stubs: { LlcBreadcrumb: true, 'router-link': true } },
  })
  await flushPromises()
  return wrapper
}

describe('BacklogView reorder + suggest-AC wiring (GH#10040)', () => {
  beforeEach(() => {
    post.mockReset()
    get.mockReset()
  })

  it('persistBacklogOrder POSTs the full desired order to the reorder endpoint', async () => {
    const wrapper = await mountView()
    post.mockResolvedValueOnce({ updated: 3 })
    const vm = wrapper.vm as unknown as BacklogVm

    // Simulate a drag of A below B → order becomes [B, A, C].
    vm.onDragStart(vm.items[0])
    await vm.onDrop(vm.items[1])
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/api/llc/companies/c1/backlog/reorder', {
      work_item_ids: ['b', 'a', 'c'],
    })
  })

  it('reverts the local order when the reorder request fails', async () => {
    const wrapper = await mountView()
    post.mockRejectedValueOnce(new Error('boom'))
    const vm = wrapper.vm as unknown as BacklogVm
    const original = vm.items.map(i => i.id)

    vm.onDragStart(vm.items[0])
    await vm.onDrop(vm.items[2])
    await flushPromises()

    expect(vm.items.map(i => i.id)).toEqual(original)
  })

  it('suggestAC POSTs title/description (never company_id) and fills suggestedACs', async () => {
    const wrapper = await mountView()
    post.mockResolvedValueOnce({ suggestions: ['Given X', 'When Y'] })
    const vm = wrapper.vm as unknown as BacklogVm
    vm.newItem.title = 'New PBI'
    vm.newItem.description = 'desc'

    await vm.suggestAC()
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/api/llc/work-items/suggest-ac', {
      title: 'New PBI',
      description: 'desc',
    })
    expect(vm.suggestedACs).toEqual([
      { text: 'Given X', selected: true },
      { text: 'When Y', selected: true },
    ])
  })

  it('suggestAC degrades to an empty list on backend failure', async () => {
    const wrapper = await mountView()
    post.mockRejectedValueOnce(new Error('LLM down'))
    const vm = wrapper.vm as unknown as BacklogVm
    vm.newItem.title = 'X'

    await vm.suggestAC()
    await flushPromises()

    expect(vm.suggestedACs).toEqual([])
  })
})
