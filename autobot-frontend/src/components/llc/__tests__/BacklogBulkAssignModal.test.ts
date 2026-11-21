// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #21791: bulk sprint assignment sends company_id, shows its failures, retries a failed sprint
// load, and ignores a sprint response that belongs to an earlier project selection.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { defineComponent, h } from 'vue'

const get = vi.fn()
const post = vi.fn()

// The kit's chrome is not under test; stand-ins render the slots and the alert message.
vi.mock('@autobot/ui', () => ({
  BaseFormField: defineComponent({
    props: { label: String },
    setup: (_p, { slots }) => () => h('div', [slots.default?.({ id: 'f' })]),
  }),
  BaseButton: defineComponent({
    inheritAttrs: false,
    props: { disabled: Boolean },
    emits: ['click'],
    setup: (p, { slots, attrs, emit }) => () =>
      h('button', { ...attrs, disabled: p.disabled, onClick: () => emit('click') }, slots.default?.()),
  }),
  BaseAlert: defineComponent({
    props: { message: String },
    setup: (p) => () => h('p', { role: 'alert' }, p.message),
  }),
  BaseModal: defineComponent({
    props: { modelValue: Boolean, title: String },
    setup: (_p, { slots }) => () => h('div', [slots.default?.(), slots.actions?.()]),
  }),
}))

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get, post }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import BacklogBulkAssignModal from '../BacklogBulkAssignModal.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages: { en: {} },
  missingWarn: false,
  fallbackWarn: false,
})
const mountOpts = { global: { plugins: [i18n], stubs: { teleport: true } } }
const PROJECTS = [
  { id: 'p-1', name: 'Alpha' },
  { id: 'p-2', name: 'Beta' },
]

function mountModal() {
  return mount(BacklogBulkAssignModal, {
    props: { modelValue: true, companyId: 'c1', workItemIds: ['w1', 'w2'], projects: PROJECTS, loadingProjects: false },
    ...mountOpts,
  })
}

async function pickProject(wrapper: ReturnType<typeof mountModal>, id: string) {
  await wrapper.findAll('select')[0].setValue(id)
  await flushPromises()
}

async function pickSprint(wrapper: ReturnType<typeof mountModal>, id: string) {
  await wrapper.findAll('select')[1].setValue(id)
}

function assignButton(wrapper: ReturnType<typeof mountModal>) {
  const buttons = wrapper.findAll('button')
  return buttons[buttons.length - 1]
}

beforeEach(() => {
  get.mockReset()
  post.mockReset()
})

describe('BacklogBulkAssignModal', () => {
  it('posts company_id with the items and the sprint', async () => {
    get.mockResolvedValue([{ id: 's-1', name: 'Sprint 1', status: 'open' }])
    post.mockResolvedValue({})
    const wrapper = mountModal()
    await pickProject(wrapper, 'p-1')
    await pickSprint(wrapper, 's-1')
    await assignButton(wrapper).trigger('click')
    await flushPromises()
    expect(post).toHaveBeenCalledTimes(1)
    expect(post.mock.calls[0][0]).toBe('/api/llc/backlog/bulk-assign-sprint')
    expect(post.mock.calls[0][1]).toEqual({ company_id: 'c1', work_item_ids: ['w1', 'w2'], sprint_id: 's-1' })
    expect(wrapper.emitted('assigned')).toHaveLength(1)
  })

  it('shows an error in the modal when the assignment fails, and does not emit assigned', async () => {
    get.mockResolvedValue([{ id: 's-1', name: 'Sprint 1', status: 'open' }])
    post.mockRejectedValue(new Error('forbidden'))
    const wrapper = mountModal()
    await pickProject(wrapper, 'p-1')
    await pickSprint(wrapper, 's-1')
    await assignButton(wrapper).trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(wrapper.find('[role="alert"]').text()).toBe('llc.backlog.assignErrorDetail')
    expect(wrapper.emitted('assigned')).toBeUndefined()
  })

  it('shows an error and a retry, not "no open sprints", when the sprint load fails', async () => {
    get.mockRejectedValueOnce(new Error('boom'))
    const wrapper = mountModal()
    await pickProject(wrapper, 'p-1')
    expect(wrapper.text()).toContain('llc.backlog.sprintsLoadFailed')
    expect(wrapper.text()).not.toContain('llc.backlog.noSprints')

    get.mockResolvedValueOnce([{ id: 's-1', name: 'Sprint 1', status: 'open' }])
    await wrapper.find('[data-testid="retry-sprints"]').trigger('click')
    await flushPromises()
    expect(get).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).not.toContain('llc.backlog.sprintsLoadFailed')
    expect(wrapper.findAll('select')[1].text()).toContain('Sprint 1')
  })

  it('ignores a sprint response from an earlier project selection', async () => {
    let resolveFirst: (v: unknown) => void = () => {}
    get.mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve }))
    get.mockResolvedValueOnce([{ id: 's-b', name: 'Beta sprint', status: 'open' }])
    const wrapper = mountModal()
    await wrapper.findAll('select')[0].setValue('p-1')
    await pickProject(wrapper, 'p-2')
    resolveFirst([{ id: 's-a', name: 'Alpha sprint', status: 'open' }])
    await flushPromises()
    const sprintSelect = wrapper.findAll('select')[1]
    expect(sprintSelect.text()).toContain('Beta sprint')
    expect(sprintSelect.text()).not.toContain('Alpha sprint')
  })
})
