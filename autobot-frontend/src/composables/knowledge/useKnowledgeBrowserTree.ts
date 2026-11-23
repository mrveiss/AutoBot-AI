// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Tree state for the Knowledge Browser (#18244).
 *
 * Moved out of KnowledgeBrowser.vue with its behaviour unchanged: load the
 * categorised facts page by page (#12394), build the nested tree, filter it by
 * main category / subcategory / the typed query, keep folders expanded across a
 * rebuild, and lazy-load a fact's full text when it is opened (#12370).
 */
import { computed, ref, type Ref } from 'vue'
import { useExpansion } from '@/composables/useExpansion'
import { useLoadingState } from '@/composables/useLoadingState'
import { useDebounce } from '@/composables/useTimeout'
import i18n from '@/i18n'
import { createLogger } from '@/utils/debugUtils'
import { formatCategoryName } from '@/utils/formatHelpers'
import type { TreeNode } from '@/components/knowledge/TreeNodeComponent.vue'
import {
  fetchFactsByCategory,
  fetchEntriesPage,
  fetchFolderContents,
  fetchFactContent,
} from '@/composables/knowledge/useKnowledgeBrowser'
import {
  buildTreeFromCategoryFacts,
  buildTreeFromEntries,
  expandedIdsForPaths,
  extractFileIdsAndNames,
  filterTreeByQuery,
  findNode,
  getExpandedPaths,
  matchesMainCategory,
  type KnowledgeFactLike,
} from '@/composables/knowledge/knowledgeTreeUtils'

const logger = createLogger('KnowledgeBrowserTree')

// Offset pagination per category (#12394); matches the prior unbounded default of 100.
const CATEGORY_FACTS_PAGE_SIZE = 100
const SEARCH_DEBOUNCE_MS = 300

type FactsByCategory = Record<string, Record<string, unknown>[]>

export interface BrowserTreeOptions {
  selectedMainCategory: Ref<string | null>
  selectedCategory: Ref<string | null>
  /** Fetch vectorization status for the given files (useKnowledgeVectorization.fetchBatchStatus). */
  fetchBatchStatus: (ids: string[], names: Map<string, string>) => Promise<boolean | void>
  /** Called when a file (not a folder) is picked, so the caller can leave the AI document editor. */
  onFilePicked?: () => void
  /** Called with a translated message when a background load fails, so the caller can show it. */
  onError?: (message: string) => void
}

const asError = (err: unknown) => (err instanceof Error ? err : new Error(String(err)))

const tr = (key: string, n?: number) => i18n.global.t(`knowledge.browser.${key}`, { n })

function useTreeLoader(opts: BrowserTreeOptions) {
  const treeData = ref<TreeNode[]>([])
  const nodeExpansion = useExpansion<string>()
  const { isLoading, wrap: loadKnowledgeTree } = useLoadingState()
  const error = ref<Error | null>(null)
  const hasMoreCategoryFacts = ref(false)
  const isLoadingMoreCategoryFacts = ref(false)
  const isRefreshingStatus = ref(false)
  const facts = ref<FactsByCategory>({})
  const offset = ref(0)
  // Bumped when a reload starts, so a page requested before it cannot merge into the new tree.
  let generation = 0

  const rebuild = () => {
    treeData.value = buildTreeFromCategoryFacts(facts.value, formatCategoryName)
  }

  /** Resolves false when the status request failed (the documents are then marked unknown). */
  const fetchStatuses = async (tree: TreeNode[]): Promise<boolean> => {
    const { ids, names } = extractFileIdsAndNames(tree)
    if (ids.length === 0) return true
    logger.info(`Fetching vectorization status for ${ids.length} documents`)
    return (await opts.fetchBatchStatus(ids, names)) !== false
  }

  const loadFirstPage = async (requestedGeneration: number) => {
    offset.value = 0
    const data = await fetchFactsByCategory({ limit: CATEGORY_FACTS_PAGE_SIZE, offset: 0 })
    if (requestedGeneration !== generation || !data || !data.categories) return
    facts.value = data.categories as FactsByCategory
    hasMoreCategoryFacts.value = Boolean(data.has_more)
    offset.value = CATEGORY_FACTS_PAGE_SIZE
    rebuild()
    await fetchStatuses(treeData.value)
  }

  const mergePage = (incoming: FactsByCategory) => {
    // Null prototype: a category named `constructor` or `__proto__` is data, not an inherited member.
    const merged: FactsByCategory = Object.assign(Object.create(null), facts.value)
    Object.keys(incoming).forEach((cat) => {
      merged[cat] = [...(merged[cat] || []), ...incoming[cat]]
    })
    facts.value = merged
  }

  const loadMoreCategoryFacts = async () => {
    if (isLoadingMoreCategoryFacts.value || !hasMoreCategoryFacts.value) return
    const requestedGeneration = generation
    isLoadingMoreCategoryFacts.value = true
    try {
      const data = await fetchFactsByCategory({ limit: CATEGORY_FACTS_PAGE_SIZE, offset: offset.value })
      if (requestedGeneration !== generation) return
      if (data && data.categories) {
        // Read at rebuild time, so a folder the user collapsed during the request stays collapsed.
        const expandedPaths = getExpandedPaths(treeData.value, nodeExpansion.expanded.value)
        mergePage(data.categories as FactsByCategory)
        hasMoreCategoryFacts.value = Boolean(data.has_more)
        offset.value += CATEGORY_FACTS_PAGE_SIZE
        rebuild()
        nodeExpansion.expandAll(expandedIdsForPaths(treeData.value, expandedPaths))
        await fetchStatuses(treeData.value)
      }
    } catch (err) {
      logger.error('Failed to load more categorized facts:', err)
      opts.onError?.(tr('loadMoreFailed'))
    } finally {
      isLoadingMoreCategoryFacts.value = false
    }
  }

  /** (Re)load the tree from the first page; a failure lands in `error`. */
  const loadTree = () => {
    error.value = null
    const requestedGeneration = ++generation
    return loadKnowledgeTree(() => loadFirstPage(requestedGeneration)).catch((err) => {
      if (requestedGeneration === generation) error.value = asError(err)
    })
  }

  const refreshVectorizationStatus = async () => {
    if (isRefreshingStatus.value) return
    isRefreshingStatus.value = true
    try {
      if (await fetchStatuses(treeData.value)) logger.info('Vectorization status refreshed')
      else opts.onError?.(tr('statusRefreshFailed'))
    } catch (err) {
      logger.error('Failed to refresh vectorization status:', err)
      opts.onError?.(tr('statusRefreshFailed'))
    } finally {
      isRefreshingStatus.value = false
    }
  }

  return {
    treeData, nodeExpansion, isLoading, error, hasMoreCategoryFacts, isLoadingMoreCategoryFacts,
    isRefreshingStatus, loadTree, loadMoreCategoryFacts, refreshVectorizationStatus,
  }
}

function useTreeFilter(treeData: Ref<TreeNode[]>, nodeExpansion: ReturnType<typeof useExpansion<string>>, opts: BrowserTreeOptions) {
  const searchQuery = ref('')
  const debouncedSearchQuery = ref('')
  const updateDebouncedSearch = useDebounce((value: string) => {
    debouncedSearchQuery.value = value
  }, SEARCH_DEBOUNCE_MS)

  const filteredTree = computed(() => {
    let tree = treeData.value.filter((n) => matchesMainCategory(n.category, opts.selectedMainCategory.value))
    if (opts.selectedCategory.value) tree = tree.filter((n) => n.category === opts.selectedCategory.value)
    if (!debouncedSearchQuery.value) return tree
    // Folders holding a match open as the query narrows.
    return filterTreeByQuery(tree, debouncedSearchQuery.value, (id) => nodeExpansion.expand(id))
  })

  const handleSearch = (query: string) => {
    searchQuery.value = query
    updateDebouncedSearch(query)
  }

  const clearSearch = () => {
    searchQuery.value = ''
    debouncedSearchQuery.value = ''
    updateDebouncedSearch.cancel()
    nodeExpansion.collapseAll()
  }

  return { searchQuery, filteredTree, handleSearch, clearSearch }
}

function useTreeContent(treeData: Ref<TreeNode[]>, nodeExpansion: ReturnType<typeof useExpansion<string>>, opts: BrowserTreeOptions) {
  const selectedFile = ref<TreeNode | null>(null)
  const fileContent = ref('')
  const { isLoading: isLoadingContent, wrap: loadFileContentOp } = useLoadingState()
  const contentError = ref<Error | null>(null)

  const loadFolderContents = async (folder: TreeNode) => {
    try {
      const data = await fetchFolderContents(folder.category || '')
      if (!Array.isArray(data.results)) return
      folder.children = (data.results as KnowledgeFactLike[]).map((item, idx) => ({
        id: `file-${folder.id}-${idx}`,
        name: (item.metadata?.title || item.metadata?.source || tr('documentFallback', idx + 1)) as string,
        type: 'file' as const,
        path: `${folder.path}/${item.metadata?.title || item.metadata?.source}`,
        size: (item.content?.length as number | undefined) || 0,
        date: item.metadata?.timestamp as string | undefined,
        category: folder.category,
        metadata: item,
      }))
    } catch (err: unknown) {
      logger.error('Failed to load folder contents:', err)
      // The folder stays empty, so opening it again retries.
      opts.onError?.(tr('folderLoadFailed'))
    }
  }

  /** The fact's full text: the snippet when it is whole, else GET /fact/{key} (#12370). */
  const resolveContent = async (file: TreeNode): Promise<string> => {
    if (file.content && !file.content.endsWith('...')) return file.content
    const factKey = file.metadata?.key || file.path?.split('/').pop()
    // No key, or the full load found nothing: a failure, not the cut-off snippet shown as if whole.
    if (!factKey) throw new Error(tr('contentUnavailable'))
    const response = await fetchFactContent(factKey)
    if (response && response.content) return response.content
    throw new Error(tr('contentUnavailable'))
  }

  // Bumped per load and by clearSelection, so only the latest load may write the pane.
  let loadSeq = 0

  const loadFileContent = async (file: TreeNode) => {
    const seq = ++loadSeq
    contentError.value = null
    fileContent.value = ''
    await loadFileContentOp(async () => {
      const text = await resolveContent(file)
      if (seq === loadSeq) fileContent.value = text
    }).catch((err) => {
      if (seq === loadSeq) contentError.value = asError(err)
    })
    if (seq === loadSeq && selectedFile.value && fileContent.value) selectedFile.value.size = fileContent.value.length
  }

  const toggleNode = (nodeId: string) => {
    const wasExpanded = nodeExpansion.isExpanded(nodeId)
    nodeExpansion.toggle(nodeId)
    if (wasExpanded) return
    const node = findNode(treeData.value, nodeId)
    if (node && node.type === 'folder' && (!node.children || node.children.length === 0)) loadFolderContents(node)
  }

  const selectNode = async (node: TreeNode) => {
    if (node.type !== 'file') return toggleNode(node.id)
    opts.onFilePicked?.()
    selectedFile.value = node
    await loadFileContent(node)
  }

  const clearSelection = () => {
    loadSeq++
    selectedFile.value = null
    fileContent.value = ''
    contentError.value = null
  }

  return { selectedFile, fileContent, isLoadingContent, contentError, toggleNode, selectNode, clearSelection }
}

/**
 * The cursor-paginated /entries tree. Not reachable from the template: since #12394 the
 * by_category tree above drives every mode. Kept wired to the composable, not deleted,
 * for the Manage listing work (#17530), the pending step that will call loadUserKnowledge and
 * loadMoreEntries; both rethrow a failed page so that screen can show it (no Manage screen exists yet).
 */
function useEntriesPaging(treeData: Ref<TreeNode[]>, nodeExpansion: ReturnType<typeof useExpansion<string>>) {
  const entries = ref<Record<string, unknown>[]>([])
  const cursor = ref('0')
  const hasMore = ref(true)
  const isLoadingMore = ref(false)

  const reset = () => {
    entries.value = []
    cursor.value = '0'
    hasMore.value = true
    isLoadingMore.value = false
  }

  const loadMore = async () => {
    if (isLoadingMore.value || !hasMore.value) return
    isLoadingMore.value = true
    try {
      const result = await fetchEntriesPage(cursor.value)
      entries.value = [...entries.value, ...result.items]
      cursor.value = result.nextCursor
      hasMore.value = result.hasMore
    } catch (err) {
      logger.error('Failed to load more entries:', err)
      throw err // a failed page is not an empty one: callers must not rebuild the tree from it
    } finally {
      isLoadingMore.value = false
    }
  }

  const loadMoreEntries = async () => {
    const paths = getExpandedPaths(treeData.value, nodeExpansion.expanded.value)
    await loadMore()
    treeData.value = buildTreeFromEntries(entries.value, formatCategoryName)
    nodeExpansion.expandAll(expandedIdsForPaths(treeData.value, paths))
  }

  const loadUserKnowledge = async () => {
    reset()
    await loadMore()
    treeData.value = buildTreeFromEntries(entries.value, formatCategoryName)
  }

  return { resetPagination: reset, loadMoreEntries, loadUserKnowledge }
}

export function useKnowledgeBrowserTree(opts: BrowserTreeOptions) {
  const loader = useTreeLoader(opts)
  const filter = useTreeFilter(loader.treeData, loader.nodeExpansion, opts)
  const content = useTreeContent(loader.treeData, loader.nodeExpansion, opts)
  const paging = useEntriesPaging(loader.treeData, loader.nodeExpansion)
  return {
    ...loader,
    ...filter,
    ...content,
    ...paging,
    expandedNodes: loader.nodeExpansion.expanded,
  }
}
