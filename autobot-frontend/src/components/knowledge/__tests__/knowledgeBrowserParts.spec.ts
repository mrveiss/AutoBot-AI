// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The leaf parts of the Refined Knowledge Browser (#18244): the one search box and its options,
 * the filter chip, the selection bar, the health strip, the tree roles and the document list.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { ref } from 'vue'
import en from '@/i18n/locales/en.json'
import KnowledgeBrowserHeader from '../KnowledgeBrowserHeader.vue'
import KnowledgeBrowserFilterBar from '../KnowledgeBrowserFilterBar.vue'
import KnowledgeBatchToolbar from '../KnowledgeBatchToolbar.vue'
import KnowledgeHealthSummary from '../KnowledgeHealthSummary.vue'
import KnowledgeSearchBar from '../KnowledgeSearchBar.vue'
import TreeNodeComponent from '../TreeNodeComponent.vue'
import KnowledgeTreePane from '../KnowledgeTreePane.vue'
import VectorizationStatusBadge from '../VectorizationStatusBadge.vue'

const stats = vi.hoisted(() => ({ value: null as unknown, refresh: vi.fn() }))
vi.mock('@/composables/knowledge/useVectorStats', async () => {
  const { computed } = await import('vue')
  return { useVectorStats: () => ({ vectorStats: computed(() => stats.value), refresh: stats.refresh }) }
})

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const global = { plugins: [i18n], stubs: { KnowledgeDocumentsBranch: true } }

function fakeSearch() {
  return {
    useRagSearch: ref(false),
    ragOptions: ref({ reformulateQuery: true, enableReranking: false, limit: 10 }),
    selectedAccessLevel: ref<string | null>(null),
    toggleAccessLevel: vi.fn(),
    clearAccessLevelFilter: vi.fn(),
  } as never
}

beforeEach(() => {
  stats.value = null
  stats.refresh.mockClear()
})

describe('KnowledgeBrowserHeader — one search box (D2)', () => {
  const header = (query = '') => mount(KnowledgeBrowserHeader, { props: { query, search: fakeSearch() }, global })

  it('has exactly one search input and an advanced options trigger', () => {
    const w = header()
    expect(w.findAll('input')).toHaveLength(1)
    expect(w.get('input').attributes('type')).toBe('search')
    expect(w.get('input').attributes('aria-label')).toBe(en.knowledge.browserHeader.searchLabel)
    expect(w.get('[data-testid="knowledge-search-options-trigger"]').classes()).toContain('adv')
  })

  it('typing emits filter; Enter emits submit', async () => {
    const w = header()
    await w.get('input').setValue('runbook')
    expect(w.emitted('filter')?.[0]).toEqual(['runbook'])
    await w.get('input').trigger('keydown', { key: 'Enter' })
    expect(w.emitted('submit')).toHaveLength(1)
  })

  it('shows the page title, subtitle and breadcrumb', () => {
    const text = header().text()
    expect(text).toContain(en.knowledge.browserHeader.title)
    expect(text).toContain(en.knowledge.browserHeader.subtitle)
    expect(text).toContain(en.knowledge.browserHeader.breadcrumb)
  })
})

describe('KnowledgeSearchBar — the options popover body', () => {
  it('toggles RAG and shows the RAG options only when it is on', async () => {
    const search = fakeSearch() as unknown as { useRagSearch: { value: boolean } }
    const w = mount(KnowledgeSearchBar, { props: { search: search as never }, global })
    expect(w.text()).not.toContain(en.knowledge.search.autoEnhanceQuery)
    search.useRagSearch.value = true
    await w.vm.$nextTick()
    expect(w.text()).toContain(en.knowledge.search.autoEnhanceQuery)
    expect(w.text()).toContain(en.knowledge.search.enableReranking)
  })

  it('an access-level chip calls toggleAccessLevel with its value', async () => {
    const search = fakeSearch() as unknown as { toggleAccessLevel: ReturnType<typeof vi.fn> }
    const w = mount(KnowledgeSearchBar, { props: { search: search as never }, global })
    await w.findAll('button').find((b) => b.text() === en.knowledge.search.accessUser)!.trigger('click')
    expect(search.toggleAccessLevel).toHaveBeenCalledWith('user')
  })
})

describe('KnowledgeBrowserFilterBar', () => {
  it('shows the chip only while a filter is on, and clears it', async () => {
    const off = mount(KnowledgeBrowserFilterBar, { props: { filterLabel: null, refreshing: false }, global })
    expect(off.text()).not.toContain('Filtering by')
    const on = mount(KnowledgeBrowserFilterBar, { props: { filterLabel: 'User Knowledge', refreshing: false }, global })
    const chip = on.get('button[aria-label="Remove filter: User Knowledge"]')
    expect(chip.text()).toContain('Filtering by: User Knowledge')
    await chip.trigger('click')
    expect(on.emitted('clear-filter')).toHaveLength(1)
  })

  it('the Status button refreshes and is disabled while refreshing', async () => {
    const w = mount(KnowledgeBrowserFilterBar, { props: { filterLabel: null, refreshing: false }, global })
    await w.get('.kb-filter-status').trigger('click')
    expect(w.emitted('refresh')).toHaveLength(1)
    await w.setProps({ refreshing: true })
    expect(w.get('.kb-filter-status').attributes('disabled')).toBeDefined()
  })
})

describe('KnowledgeBatchToolbar — the one selection bar', () => {
  const bar = (props: Record<string, unknown> = {}) =>
    mount(KnowledgeBatchToolbar, {
      props: { hasSelection: true, selectionCount: 3, canVectorize: true, ...props },
      global,
    })

  it('is absent without a selection', () => {
    expect(bar({ hasSelection: false }).find('.batch-toolbar').exists()).toBe(false)
  })

  it('is advanced-only and counts the selection', () => {
    const w = bar()
    expect(w.get('.batch-toolbar').classes()).toContain('adv')
    expect(w.text()).toContain('3 document(s) selected')
  })

  it('notes the eligible count only when it is below the selection', () => {
    expect(bar({ eligibleCount: 3 }).find('.batch-eligible').exists()).toBe(false)
    expect(bar({ eligibleCount: 1 }).get('.batch-eligible').text()).toBe('1 eligible')
  })

  it('emits vectorize and deselect-all; vectorize is disabled when nothing can be vectorized', async () => {
    const w = bar()
    await w.get('.batch-vectorize').trigger('click')
    await w.findAll('button').find((b) => b.text() === en.knowledge.batchToolbar.clearSelection)!.trigger('click')
    expect(w.emitted('vectorize')).toHaveLength(1)
    expect(w.emitted('deselect-all')).toHaveLength(1)
    expect(bar({ canVectorize: false }).get('.batch-vectorize').attributes('disabled')).toBeDefined()
  })
})

describe('KnowledgeHealthSummary', () => {
  it('shows the stats the backend serves, as an advanced region, and refreshes on mount', () => {
    stats.value = { total_facts: 15184, total_vectors: 184302, db_size: 2048, rag_available: true }
    const w = mount(KnowledgeHealthSummary, { global })
    expect(w.classes()).toContain('adv')
    expect(w.text()).toContain('15,184')
    expect(w.text()).toContain('184,302')
    expect(w.text()).toContain(en.knowledge.healthSummary.ragAvailable)
    expect(stats.refresh).toHaveBeenCalledTimes(1)
  })

  it('shows zeros and RAG unavailable before any stats exist, and draws no figure it has no source for', () => {
    const w = mount(KnowledgeHealthSummary, { global })
    expect(w.text()).toContain(en.knowledge.healthSummary.ragUnavailable)
    expect(w.text()).not.toMatch(/Quality|Warnings/)
  })
})

describe('TreeNodeComponent — tree roles', () => {
  const props = (node: object, extra: object = {}) => ({
    node, expandedNodes: new Set<string>(), selectedDocuments: new Set<string>(), vectorizationStates: new Map(), ...extra,
  })
  const folder = { id: 'd', name: 'projects', type: 'folder', path: '/projects', children: [{ id: 'f', name: 'a.md', type: 'file', path: '/projects/a.md' }] }

  it('a folder is a treeitem with aria-expanded; its children sit in a group one level deeper', () => {
    const closed = mount(TreeNodeComponent, { props: props(folder), global })
    expect(closed.get('[role="treeitem"]').attributes('aria-expanded')).toBe('false')
    expect(closed.find('[role="group"]').exists()).toBe(false)
    const open = mount(TreeNodeComponent, { props: props(folder, { expandedNodes: new Set(['d']) }), global })
    expect(open.get('[role="treeitem"]').attributes('aria-expanded')).toBe('true')
    const child = open.get('[role="group"] [role="treeitem"]')
    expect(child.attributes('aria-level')).toBe('2')
    expect(child.attributes('aria-expanded')).toBeUndefined()
  })

  it('marks the selected node and names each checkbox by its file', async () => {
    const w = mount(TreeNodeComponent, { props: props(folder.children[0], { selectedId: 'f' }), global })
    expect(w.get('[role="treeitem"]').attributes('aria-selected')).toBe('true')
    const box = w.get('input[type="checkbox"]')
    expect(box.attributes('aria-label')).toBe('Select a.md')
    await box.trigger('click')
    expect(w.emitted('toggle-select')?.[0]).toEqual(['f'])
  })

  it('clicking a name emits select; a not-yet-vectorized file offers Vectorize', async () => {
    const w = mount(TreeNodeComponent, { props: props(folder.children[0]), global })
    await w.get('.node-name-btn').trigger('click')
    expect(w.emitted('select')?.[0][0]).toMatchObject({ id: 'f' })
    await w.get('.vectorize-btn').trigger('click')
    expect(w.emitted('vectorize')?.[0]).toEqual(['f'])
  })

  it('status pills are advanced-only; a vectorized file offers no Vectorize', () => {
    const states = new Map([['f', { status: 'vectorized' }]])
    const w = mount(TreeNodeComponent, { props: props(folder.children[0], { vectorizationStates: states }), global })
    expect(w.find('.vectorize-btn').exists()).toBe(false)
    expect(w.find('.adv .vectorization-badge').exists()).toBe(true)
  })
})

describe('VectorizationStatusBadge', () => {
  it.each([
    ['vectorized', 'Vectorized'],
    ['pending', 'Pending'],
    ['failed', 'Failed'],
    ['unknown', 'Unknown'],
  ])('%s reads "%s", with the label hidden for the compact form', (status, label) => {
    const labelled = mount(VectorizationStatusBadge, { props: { status: status as never, showLabel: true }, global })
    expect(labelled.get('.badge-label').text()).toBe(label)
    const compact = mount(VectorizationStatusBadge, { props: { status: status as never }, global })
    expect(compact.find('.badge-label').exists()).toBe(false)
    expect(compact.get('.sr-only').text()).toBe(label)
  })
})

describe('KnowledgeTreePane', () => {
  const base = {
    isLoading: false, error: null, nodes: [], expandedNodes: new Set<string>(), selectedDocuments: new Set<string>(),
    vectorizationStates: new Map(), hasMore: false, isLoadingMore: false, selectedDocId: null,
  }

  it('shows a loading state, then an error with Retry, then the empty state', async () => {
    expect(mount(KnowledgeTreePane, { props: { ...base, isLoading: true }, global }).text()).toContain('Loading file tree')
    const err = mount(KnowledgeTreePane, { props: { ...base, error: new Error('nope') }, global })
    expect(err.text()).toContain('nope')
    await err.get('button').trigger('click')
    expect(err.emitted('retry')).toHaveLength(1)
    expect(mount(KnowledgeTreePane, { props: base, global }).text()).toContain(en.knowledge.browser.noItemsFound)
  })

  it('renders a tree with Load More only while more pages exist, and the AI documents branch under it', async () => {
    const nodes = [{ id: 'f', name: 'a.md', type: 'file', path: '/a.md' }]
    const w = mount(KnowledgeTreePane, { props: { ...base, nodes, hasMore: true }, global })
    expect(w.get('[role="tree"]').attributes('aria-label')).toBe(en.knowledge.browser.treeLabel)
    expect(w.findAll('[role="treeitem"]')).toHaveLength(1)
    await w.findAll('button').find((b) => b.text() === en.knowledge.browser.loadMore)!.trigger('click')
    expect(w.emitted('load-more')).toHaveLength(1)
    expect(w.find('knowledge-documents-branch-stub').exists()).toBe(true)
    await w.setProps({ hasMore: false })
    expect(w.findAll('button').some((b) => b.text() === en.knowledge.browser.loadMore)).toBe(false)
  })
})
