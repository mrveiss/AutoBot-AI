// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Tree state of the Knowledge Browser (#18244), pinned against the behaviour
 * KnowledgeBrowser.vue had before it moved: paging (#12394), expansion kept across a
 * rebuild, the main-category filter, the debounced query, lazy content (#12370).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'

const h = vi.hoisted(() => ({
  fetchFactsByCategory: vi.fn(),
  fetchEntriesPage: vi.fn(),
  fetchFolderContents: vi.fn(),
  fetchFactContent: vi.fn(),
}))
vi.mock('@/composables/knowledge/useKnowledgeBrowser', () => h)

import { useKnowledgeBrowserTree } from '../useKnowledgeBrowserTree'

const fact = (name: string, key: string, content = 'short') => ({ key, title: name, content, metadata: { filename: name } })
const PAGE1 = { categories: { autobot_docs: [fact('docs/a.md', 'fact:a')], cooking: [fact('pasta.md', 'fact:p')] }, has_more: true }
const PAGE2 = { categories: { cooking: [fact('rice.md', 'fact:r')] }, has_more: false }

function make(extra: Partial<Parameters<typeof useKnowledgeBrowserTree>[0]> = {}) {
  const fetchBatchStatus = vi.fn().mockResolvedValue(undefined)
  const selectedMainCategory = ref<string | null>(null)
  const selectedCategory = ref<string | null>(null)
  const tree = useKnowledgeBrowserTree({ selectedMainCategory, selectedCategory, fetchBatchStatus, ...extra })
  return { tree, fetchBatchStatus, selectedMainCategory, selectedCategory }
}

beforeEach(() => {
  vi.clearAllMocks()
  h.fetchFactsByCategory.mockResolvedValueOnce(PAGE1)
})
afterEach(() => vi.useRealTimers())

describe('loading', () => {
  it('builds one folder per category from the first page and asks for every file\'s status', async () => {
    const { tree, fetchBatchStatus } = make()
    await tree.loadTree()
    expect(h.fetchFactsByCategory).toHaveBeenCalledWith({ limit: 100, offset: 0 })
    expect(tree.treeData.value.map((n) => n.category)).toEqual(['autobot_docs', 'cooking'])
    expect(tree.hasMoreCategoryFacts.value).toBe(true)
    expect([...fetchBatchStatus.mock.calls[0][0]].sort()).toEqual(['a', 'p'])
  })

  it('puts a failed load in `error` rather than throwing', async () => {
    h.fetchFactsByCategory.mockReset().mockRejectedValue(new Error('down'))
    const { tree } = make()
    await tree.loadTree()
    expect(tree.error.value?.message).toBe('down')
    await tree.loadTree()
    expect(tree.isLoading.value).toBe(false)
  })

  it('Load More merges the next page and keeps expanded folders open', async () => {
    h.fetchFactsByCategory.mockResolvedValueOnce(PAGE2)
    const { tree } = make()
    await tree.loadTree()
    tree.nodeExpansion.expand('folder-1') // cooking
    await tree.loadMoreCategoryFacts()
    expect(h.fetchFactsByCategory).toHaveBeenLastCalledWith({ limit: 100, offset: 100 })
    expect(tree.treeData.value[1].children?.map((n) => n.name)).toEqual(['pasta.md', 'rice.md'])
    expect(tree.expandedNodes.value.has('folder-1')).toBe(true)
    expect(tree.hasMoreCategoryFacts.value).toBe(false)
    await tree.loadMoreCategoryFacts() // nothing more: no third fetch
    expect(h.fetchFactsByCategory).toHaveBeenCalledTimes(2)
  })
})

describe('filtering', () => {
  it('filters by main category, then by subcategory', async () => {
    const { tree, selectedMainCategory, selectedCategory } = make()
    await tree.loadTree()
    selectedMainCategory.value = 'user-knowledge'
    expect(tree.filteredTree.value.map((n) => n.category)).toEqual(['cooking'])
    selectedMainCategory.value = null
    selectedCategory.value = 'autobot_docs'
    expect(tree.filteredTree.value.map((n) => n.category)).toEqual(['autobot_docs'])
  })

  it('filters by the typed query after the debounce, and opens the folders that hold a match', async () => {
    vi.useFakeTimers()
    const { tree } = make()
    await tree.loadTree()
    tree.handleSearch('PASTA')
    expect(tree.filteredTree.value).toHaveLength(2) // not yet: debounced
    await vi.advanceTimersByTimeAsync(300)
    expect(tree.filteredTree.value.map((n) => n.category)).toEqual(['cooking'])
    expect(tree.expandedNodes.value.has('folder-1')).toBe(true)
  })

  it('clearSearch resets the query and collapses everything', async () => {
    vi.useFakeTimers()
    const { tree } = make()
    await tree.loadTree()
    tree.nodeExpansion.expand('folder-0')
    tree.handleSearch('pasta')
    tree.clearSearch()
    await vi.advanceTimersByTimeAsync(400)
    expect(tree.searchQuery.value).toBe('')
    expect(tree.filteredTree.value).toHaveLength(2)
    expect(tree.expandedNodes.value.size).toBe(0)
  })
})

describe('opening nodes', () => {
  it('a folder click toggles it; a file click selects it, leaves the editor and shows the snippet', async () => {
    const onFilePicked = vi.fn()
    const { tree } = make({ onFilePicked })
    await tree.loadTree()
    const folder = tree.treeData.value[1]
    await tree.selectNode(folder)
    expect(tree.expandedNodes.value.has(folder.id)).toBe(true)
    const file = folder.children![0]
    await tree.selectNode(file)
    expect(onFilePicked).toHaveBeenCalledTimes(1)
    expect(tree.selectedFile.value?.id).toBe('p')
    expect(tree.fileContent.value).toBe('short')
    expect(h.fetchFactContent).not.toHaveBeenCalled()
  })

  it('lazy-loads the full text of a truncated snippet from the fact endpoint', async () => {
    h.fetchFactsByCategory.mockReset().mockResolvedValue({ categories: { c: [fact('long.md', 'fact:l', 'cut...')] } })
    h.fetchFactContent.mockResolvedValue({ content: 'the whole document' })
    const { tree } = make()
    await tree.loadTree()
    await tree.selectNode(tree.treeData.value[0].children![0])
    expect(h.fetchFactContent).toHaveBeenCalledWith('fact:l')
    expect(tree.fileContent.value).toBe('the whole document')
  })

  it('a failed content load lands in contentError; clearSelection resets the pane', async () => {
    h.fetchFactsByCategory.mockReset().mockResolvedValue({ categories: { c: [fact('long.md', 'fact:l', 'cut...')] } })
    h.fetchFactContent.mockRejectedValue(new Error('gone'))
    const { tree } = make()
    await tree.loadTree()
    await tree.selectNode(tree.treeData.value[0].children![0])
    expect(tree.contentError.value?.message).toBe('gone')
    tree.clearSelection()
    expect([tree.selectedFile.value, tree.fileContent.value, tree.contentError.value]).toEqual([null, '', null])
  })

  it('opening an empty folder fetches its contents', async () => {
    h.fetchFactsByCategory.mockReset().mockResolvedValue({ categories: { empty: [] } })
    h.fetchFolderContents.mockResolvedValue({ results: [{ content: 'x', metadata: { title: 'doc.md' } }] })
    const { tree } = make()
    await tree.loadTree()
    tree.toggleNode('folder-0')
    await vi.waitFor(() => expect(tree.treeData.value[0].children).toHaveLength(1))
    expect(h.fetchFolderContents).toHaveBeenCalledWith('empty')
  })
})

describe('refreshing statuses', () => {
  it('re-fetches the status of every file once, ignoring a second call while busy', async () => {
    const { tree, fetchBatchStatus } = make()
    await tree.loadTree()
    fetchBatchStatus.mockClear()
    await Promise.all([tree.refreshVectorizationStatus(), tree.refreshVectorizationStatus()])
    expect(fetchBatchStatus).toHaveBeenCalledTimes(1)
    expect(tree.isRefreshingStatus.value).toBe(false)
  })
})
