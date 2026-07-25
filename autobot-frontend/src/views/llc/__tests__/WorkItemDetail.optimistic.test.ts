// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #12348: WorkItemDetail edits (title / description / acceptance-criteria) are
// applied optimistically through v-model before the PATCH lands. These tests
// assert that a rejected PATCH rolls the local state back to its last-persisted
// value and surfaces an i18n error, mirroring the chat-delete fix (#12327).

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const patch = vi.fn()
const get = vi.fn()
const post = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get, post, patch }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

// The assignee picker fetches org people on mount; keep it inert for these tests.
vi.mock('@/composables/llc/useCompanyPeople', () => ({
  useCompanyPeople: () => ({
    agents: { value: [] },
    humans: { value: [] },
    isLoading: { value: false },
    load: vi.fn(),
  }),
}))

import WorkItemDetail from '../WorkItemDetail.vue'

interface DetailVm {
  localItem: {
    title: string
    description: string
    acceptance_criteria: string[]
    acceptance_criteria_done?: boolean[]
  }
  checkedAC: boolean[]
  saveError: string | null
  startEditTitle: () => void
  saveTitle: () => Promise<void>
  startEditDesc: () => void
  saveDesc: () => Promise<void>
  saveAC: () => Promise<void>
}

const ITEM = {
  id: 'w1',
  identifier: 'WI-1',
  title: 'Original title',
  description: 'Original description',
  type: 'pbi',
  status: 'new',
  priority: 'medium',
  acceptance_criteria: ['Criterion A', 'Criterion B'],
  acceptance_criteria_done: [false, false],
}

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
const SAVE_FAILED = en.llc.workItem.errors.saveFailed

async function mountDetail() {
  const wrapper = mount(WorkItemDetail, {
    props: { item: { ...ITEM }, companyId: 'c1' },
    global: {
      plugins: [i18n],
      stubs: { HandoffModal: true, WorkItemBadge: true },
    },
  })
  await flushPromises()
  return wrapper
}

describe('WorkItemDetail optimistic-edit rollback (#12348)', () => {
  beforeEach(() => {
    patch.mockReset()
    get.mockReset()
    post.mockReset()
  })

  it('rolls the title back and surfaces an error when the PATCH fails', async () => {
    const wrapper = await mountDetail()
    const vm = wrapper.vm as unknown as DetailVm
    patch.mockRejectedValueOnce(new Error('boom'))

    vm.startEditTitle() // captures origTitle = 'Original title'
    vm.localItem.title = 'Edited title' // what v-model would have written
    await vm.saveTitle()
    await flushPromises()

    expect(patch).toHaveBeenCalledWith('/api/llc/work-items/w1', { title: 'Edited title' })
    expect(vm.localItem.title).toBe('Original title')
    expect(vm.saveError).toBe(SAVE_FAILED)
  })

  it('keeps the edited title and clears the error when the PATCH succeeds', async () => {
    const wrapper = await mountDetail()
    const vm = wrapper.vm as unknown as DetailVm
    patch.mockResolvedValueOnce({ ...ITEM, title: 'Edited title' })

    vm.startEditTitle()
    vm.localItem.title = 'Edited title'
    await vm.saveTitle()
    await flushPromises()

    expect(vm.localItem.title).toBe('Edited title')
    expect(vm.saveError).toBeNull()
  })

  it('rolls the description back when the PATCH fails', async () => {
    const wrapper = await mountDetail()
    const vm = wrapper.vm as unknown as DetailVm
    patch.mockRejectedValueOnce(new Error('boom'))

    vm.startEditDesc() // captures origDesc = 'Original description'
    vm.localItem.description = 'Edited description'
    await vm.saveDesc()
    await flushPromises()

    expect(vm.localItem.description).toBe('Original description')
    expect(vm.saveError).toBe(SAVE_FAILED)
  })

  it('rolls the acceptance-criteria checkbox back when the PATCH fails', async () => {
    const wrapper = await mountDetail()
    const vm = wrapper.vm as unknown as DetailVm
    patch.mockRejectedValueOnce(new Error('boom'))

    // Mounted state hydrates checkedAC from acceptance_criteria_done ([false, false]).
    vm.checkedAC[0] = true // what the checkbox v-model would have written
    await vm.saveAC()
    await flushPromises()

    expect(patch).toHaveBeenCalledWith('/api/llc/work-items/w1', {
      acceptance_criteria_done: [true, false],
    })
    expect(vm.checkedAC).toEqual([false, false])
    expect(vm.saveError).toBe(SAVE_FAILED)
  })
})
