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
  fetchBatchStatus: (ids: string[], names: Map<string, string>) => Promise<unknown>
  /** Called when a file (not a folder) is picked, so the caller can leave the AI document editor. */
  onFilePicked?: () => void
}

const asError = (err: unknown) => (err instanceof Error ? err : new Error(String(err)))

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

  const rebuild = () => {
    treeData.value = buildTreeFromCategoryFacts(facts.value, formatCategoryName)
  }

  const fetchStatuses = async (tree: TreeNode[]) => {
    const { ids, names } = extractFileIdsAndNames(tree)
    if (ids.length > 0) {
      logger.info(`Fetching vectorization status for ${ids.length} documents`)
      await opts.fetchBatchStatus(ids, names)
    }
  }

  const loadFirstPage = async () => {
    offset.value = 0
    const data = await fetchFactsByCategory({ limit: CATEGORY_FACTS_PAGE_SIZE, offset: 0 })
    if (!data || !data.categories) return
    facts.value = data.categories as FactsByCategory
    hasMoreCategoryFacts.value = Boolean(data.has_more)
    offset.value = CATEGORY_FACTS_PAGE_SIZE
    rebuild()
    await fetchStatuses(treeData.value)
  }

  const mergePage = (incoming: FactsByCategory) => {
    const merged = { ...facts.value }
    Object.keys(incoming).forEach((cat) => {
      merged[cat] = [...(merged[cat] || []), ...incoming[cat]]
    })
    facts.value = merged
  }

  const loadMoreCategoryFacts = async () => {
    if (isLoadingMoreCategoryFacts.value || !hasMoreCategoryFacts.value) return
    const expandedPaths = getExpandedPaths(treeData.value, nodeExpansion.expanded.value)
    isLoadingMoreCategoryFacts.value = true
    try {
      const data = await fetchFactsByCategory({ limit: CATEGORY_FACTS_PAGE_SIZE, offset: offset.value })
      if (data && data.categories) {
        mergePage(data.categories as FactsByCategory)
        hasMoreCategoryFacts.value = Boolean(data.has_more)
        offset.value += CATEGORY_FACTS_PAGE_SIZE
        rebuild()
        nodeExpansion.expandAll(expandedIdsForPaths(treeData.value, expandedPaths))
        await fetchStatuses(treeData.value)
      }
    } catch (err) {
      logger.error('Failed to load more categorized facts:', err)
    } finally {
      isLoadingMoreCategoryFacts.value = false
    }
  }

  /** (Re)load the tree from the first page; a failure lands in `error`. */
  const loadTree = () => {
    error.value = null
    return loadKnowledgeTree(loadFirstPage).catch((err) => {
      error.value = asError(err)
    })
  }

  const refreshVectorizationStatus = async () => {
    if (isRefreshingStatus.value) return
    isRefreshingStatus.value = true
    try {
      await fetchStatuses(treeData.value)
      logger.info('Vectorization status refreshed')
    } catch (err) {
      logger.error('Failed to refresh vectorization status:', err)
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
        name: (item.metadata?.title || item.metadata?.source || `Document ${idx + 1}`) as string,
        type: 'file' as const,
        path: `${folder.path}/${item.metadata?.title || item.metadata?.source}`,
        size: (item.content?.length as number | undefined) || 0,
        date: item.metadata?.timestamp as string | undefined,
        category: folder.category,
        metadata: item,
      }))
    } catch (err: unknown) {
      logger.error('Failed to load folder contents:', err)
    }
  }

  /** The fact's full text: the snippet when it is whole, else GET /fact/{key} (#12370). */
  const resolveContent = async (file: TreeNode): Promise<string> => {
    if (file.content && !file.content.endsWith('...')) return file.content
    const factKey = file.metadata?.key || file.path?.split('/').pop()
    if (!factKey) return file.content || 'Content not available'
    const response = await fetchFactContent(factKey)
    return response && response.content ? response.content : file.content || 'Content not available'
  }

  const loadFileContent = async (file: TreeNode) => {
    contentError.value = null
    await loadFileContentOp(async () => {
      fileContent.value = await resolveContent(file)
    }).catch((err) => {
      contentError.value = asError(err)
    })
    if (selectedFile.value && fileContent.value) selectedFile.value.size = fileContent.value.length
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
    selectedFile.value = null
    fileContent.value = ''
    contentError.value = null
  }

  return { selectedFile, fileContent, isLoadingContent, contentError, toggleNode, selectNode, clearSelection }
}

/**
 * The cursor-paginated /entries tree. Not reachable from the template: since #12394 the
 * by_category tree above drives every mode. Kept wired to the composable, not deleted,
 * for the Manage listing work (#17530).
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
