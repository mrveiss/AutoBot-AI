// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #18978: every work item belongs to a project, so the backlog create form needs one.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { defineComponent, h } from 'vue'

const post = vi.fn()

// The kit's modal chrome is not under test; a stand-in that renders its body and
// actions slots keeps this test off the kit's other dependencies.
vi.mock('@autobot/ui', () => ({
  BaseModal: defineComponent({
    props: { modelValue: Boolean, title: String },
    setup: (_p, { slots }) => () => h('div', [slots.default?.(), slots.actions?.()]),
  }),
}))

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ post }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import BacklogCreateModal from '../BacklogCreateModal.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages: { en: {} },
  missingWarn: false,
  fallbackWarn: false,
})
// BaseModal teleports to body; render it inline so wrapper.find() reaches the form.
const mountOpts = { global: { plugins: [i18n], stubs: { teleport: true } } }

const PROJECTS = [
  { id: 'p-1', name: 'Alpha' },
  { id: 'p-2', name: 'Beta' },
]

function mountForm(props: Record<string, unknown> = {}) {
  return mount(BacklogCreateModal, {
    props: {
      modelValue: true,
      companyId: 'c1',
      projects: PROJECTS,
      loadingProjects: false,
      defaultProjectId: '',
      ...props,
    },
    ...mountOpts,
  })
}

const createButton = (w: ReturnType<typeof mountForm>) =>
  w.findAll('button').find((b) => b.text() === 'common.create')!

describe('BacklogCreateModal (#18978)', () => {
  beforeEach(() => {
    post.mockReset()
    post.mockResolvedValue({ id: 'wi-1', title: 'T' })
  })

  it('keeps Create disabled until a project is chosen', async () => {
    const w = mountForm()
    await w.find('input[type="text"]').setValue('A title')
    expect(createButton(w).attributes('disabled')).toBeDefined()

    await w.find('select').setValue('p-2')
    expect(createButton(w).attributes('disabled')).toBeUndefined()
  })

  it('posts the chosen project_id', async () => {
    const w = mountForm()
    await w.find('input[type="text"]').setValue('A title')
    await w.find('select').setValue('p-2')
    await createButton(w).trigger('click')
    await flushPromises()

    expect(post).toHaveBeenCalledWith(
      '/api/llc/work-items',
      expect.objectContaining({ company_id: 'c1', title: 'A title', project_id: 'p-2' }),
    )
    expect(w.emitted('created')).toHaveLength(1)
  })

  it('prefills the project from the backlog filter', async () => {
    const w = mountForm({ defaultProjectId: 'p-1' })
    await w.find('input[type="text"]').setValue('A title')
    expect(createButton(w).attributes('disabled')).toBeUndefined()
    await createButton(w).trigger('click')
    await flushPromises()
    expect(post).toHaveBeenCalledWith('/api/llc/work-items', expect.objectContaining({ project_id: 'p-1' }))
  })

  it('tells the user what to do when the company has no project, and cannot create', async () => {
    const w = mountForm({ projects: [] })
    await w.find('input[type="text"]').setValue('A title')
    expect(w.text()).toContain('llc.backlog.noProjectsHint')
    expect(createButton(w).attributes('disabled')).toBeDefined()
    expect(post).not.toHaveBeenCalled()
  })
})
