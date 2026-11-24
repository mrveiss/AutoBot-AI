// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/** KnowledgeDocumentsBranch (#11526 / #18244): the AI documents listbox beside the tree. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { ref } from 'vue'
import en from '@/i18n/locales/en.json'

const h = vi.hoisted(() => ({ fetchDocuments: vi.fn(), deleteDocument: vi.fn() }))
vi.mock('vue-router', () => ({ RouterLink: { template: '<a><slot /></a>' } }))
vi.mock('@/composables/useAIDocument', () => ({
  useAIDocument: () => ({
    documents: ref([
      { id: 'd1', title: 'Fleet runbook', updated_at: '2026-10-10T10:58:00Z' },
      { id: 'd2', title: 'NPU benchmarks', updated_at: '2026-10-08T09:00:00Z' },
    ]),
    isLoading: ref(false),
    hasDocuments: ref(true),
    total: ref(2),
    error: ref(null),
    fetchDocuments: h.fetchDocuments,
    deleteDocument: h.deleteDocument,
  }),
}))
vi.mock('@/composables/transcriber/useTranscriberApi', () => ({ useTranscriberApi: () => ({ listProjects: vi.fn().mockResolvedValue([]) }) }))

import KnowledgeDocumentsBranch from '../KnowledgeDocumentsBranch.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const mountBranch = (selectedDocId: string | null = null) =>
  mount(KnowledgeDocumentsBranch, { props: { selectedDocId }, global: { plugins: [i18n] }, attachTo: document.body })

beforeEach(() => {
  vi.clearAllMocks()
  h.fetchDocuments.mockResolvedValue(undefined)
})

describe('KnowledgeDocumentsBranch', () => {
  it('is a labelled listbox of options; the open document is aria-selected', async () => {
    const w = mountBranch('d2')
    await flushPromises()
    expect(w.get('[role="listbox"]').attributes('aria-label')).toBe(en.documents.listAriaLabel)
    const options = w.findAll('[role="option"]')
    expect(options.map((o) => o.attributes('aria-selected'))).toEqual(['false', 'true'])
    expect(options[0].text()).toContain('Fleet runbook')
  })

  it('selecting a row emits its id; the refresh button reloads the page', async () => {
    const w = mountBranch()
    await flushPromises()
    await w.findAll('[role="option"]')[0].trigger('click')
    expect(w.emitted('select')?.[0]).toEqual(['d1'])
    await w.get('.refresh-btn').trigger('click')
    expect(h.fetchDocuments).toHaveBeenLastCalledWith(50, 0)
  })

  it('delete asks first, then deletes and reports the id', async () => {
    h.deleteDocument.mockResolvedValue(undefined)
    const w = mountBranch()
    await flushPromises()
    await w.findAll('.delete-btn')[0].trigger('click')
    await flushPromises()
    expect(h.deleteDocument).not.toHaveBeenCalled()
    const confirm = Array.from(document.body.querySelectorAll('button')).find((b) => b.textContent?.trim() === en.common.delete)
    confirm!.click()
    await flushPromises()
    expect(h.deleteDocument).toHaveBeenCalledWith('d1')
    expect(w.emitted('deleted')?.[0]).toEqual(['d1'])
    w.unmount()
  })
})
