// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * KnowledgeBrowser (#18244): the screen composes ONE header with ONE search box, ONE category
 * control (the cards) with ONE filter chip, and ONE selection bar; Enter in the box runs the
 * unified search, typing filters the tree.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createPinia } from 'pinia'
import { ref } from 'vue'
import en from '@/i18n/locales/en.json'

const h = vi.hoisted(() => ({
  fetchMainCategories: vi.fn(),
  fetchFactsByCategory: vi.fn(),
  handleSearch: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {}, params: {} }),
  useRouter: () => ({ push: vi.fn() }),
  RouterLink: { template: '<a><slot /></a>' },
}))
vi.mock('@/composables/knowledge/useKnowledgeBrowser', () => ({
  fetchMainCategories: h.fetchMainCategories,
  fetchFactsByCategory: h.fetchFactsByCategory,
  fetchEntriesPage: vi.fn(),
  fetchFolderContents: vi.fn(),
  fetchFactContent: vi.fn(),
}))
vi.mock('@/composables/useKnowledgeVectorization', () => ({
  useKnowledgeVectorization: () => ({
    documentStates: ref(new Map()),
    selectedDocuments: ref(new Set<string>(['a'])),
    selectedDocumentsList: ref(['a']),
    hasSelection: ref(true),
    selectionCount: ref(1),
    canVectorizeSelection: ref(true),
    toggleDocumentSelection: vi.fn(),
    deselectAll: vi.fn(),
    fetchBatchStatus: vi.fn(),
    getDocumentStatus: vi.fn(),
    vectorizeDocument: vi.fn(),
    vectorizeBatch: vi.fn(),
    vectorizeSelected: vi.fn(),
    cleanup: vi.fn(),
  }),
}))
vi.mock('@/composables/knowledge/useKnowledgeSearch', async () => {
  const { ref: r } = await import('vue')
  return {
    useKnowledgeSearch: () => ({
      searchQuery: r(''),
      useRagSearch: r(false),
      ragOptions: r({ reformulateQuery: true, enableReranking: false, limit: 10 }),
      selectedAccessLevel: r(null),
      searchPerformed: r(false),
      isSearching: r(false),
      searchResults: r([]),
      lastSearchQuery: r(''),
      ragResponse: r(null),
      ragError: r(null),
      toggleAccessLevel: vi.fn(),
      clearAccessLevelFilter: vi.fn(),
      clearResults: vi.fn(),
      handleSearch: h.handleSearch,
    }),
  }
})

import KnowledgeBrowser from '../KnowledgeBrowser.vue'

const CATEGORIES = [
  { id: 'autobot-documentation', name: 'AutoBot Documentation', description: 'd', icon: 'book', color: '', count: 3 },
  { id: 'user-knowledge', name: 'User Knowledge', description: 'u', icon: 'user-circle', color: '', count: 5 },
]
const fact = (name: string, key: string) => ({ key, title: name, content: 'x', metadata: { filename: name } })

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const stubs = { KnowledgeHealthSummary: true, KnowledgeDocumentsBranch: true, CategoryEditModal: true, VectorizationProgressModal: true, AIDocumentEditor: true }

async function mountBrowser() {
  const w = mount(KnowledgeBrowser, { global: { plugins: [i18n, createPinia()], stubs } })
  await flushPromises()
  return w
}

beforeEach(() => {
  vi.clearAllMocks()
  h.fetchMainCategories.mockResolvedValue({ categories: CATEGORIES, kb_connected: true })
  h.fetchFactsByCategory.mockResolvedValue({
    categories: { autobot_docs: [fact('docs/a.md', 'fact:a')], cooking: [fact('pasta.md', 'fact:p')] },
    has_more: false,
  })
})

describe('KnowledgeBrowser', () => {
  it('has exactly one search input and one category control', async () => {
    const w = await mountBrowser()
    expect(w.findAll('input[type="search"]')).toHaveLength(1)
    expect(w.findAll('.main-category-card')).toHaveLength(2)
    expect(w.find('.category-tabs').exists()).toBe(false)
    expect(w.findAll('.batch-toolbar')).toHaveLength(1)
  })

  it('draws the tree from the loaded categories', async () => {
    const w = await mountBrowser()
    expect(w.get('[role="tree"]').findAll('[role="treeitem"]')).toHaveLength(2)
  })

  it('choosing a card filters the tree and shows one filter chip that removes it', async () => {
    const w = await mountBrowser()
    expect(w.find('.kb-filter-chip').exists()).toBe(false)
    await w.findAll('.card-select')[1].trigger('click') // User Knowledge -> cooking only
    expect(w.get('[role="tree"]').findAll('[role="treeitem"]')).toHaveLength(1)
    expect(w.findAll('.kb-filter-chip')).toHaveLength(1)
    expect(w.get('.kb-filter-chip').text()).toContain('User Knowledge')
    await w.get('.kb-filter-chip').trigger('click')
    expect(w.get('[role="tree"]').findAll('[role="treeitem"]')).toHaveLength(2)
    expect(w.find('.kb-filter-chip').exists()).toBe(false)
  })

  it('Enter in the box runs the unified search with the typed text', async () => {
    const w = await mountBrowser()
    await w.get('input[type="search"]').setValue('runbook')
    await w.get('input[type="search"]').trigger('keydown', { key: 'Enter' })
    expect(h.handleSearch).toHaveBeenCalledTimes(1)
  })

  it('shows the selection bar with the selected count', async () => {
    const w = await mountBrowser()
    expect(w.get('.batch-toolbar').text()).toContain('1 document(s) selected')
  })

  it('shows the placeholder reading pane until a file is picked', async () => {
    const w = await mountBrowser()
    expect(w.text()).toContain(en.knowledge.contentViewer.noFileSelected)
  })
})
