<template>
  <div class="knowledge-file-browser">
    <!-- Main Categories -->
    <KnowledgeMainCategories
      :categories="mainCategories"
      :population-states="populationStates"
      :kb-connected="kbConnected"
      :kb-fetch-error="kbFetchError"
      @select="selectMainCategory"
      @populate="handlePopulate"
      @import="() => router.push('/knowledge/upload')"
    />

    <!-- Header -->
    <div class="browser-header">
      <!-- Category Filter Tabs with enhanced transitions (Issue #161) -->
      <div class="category-tabs-container">
        <KnowledgeBrowserHeader
          :categories="availableCategories"
          :selected-category="selectedCategory"
          :search-query="searchQuery"
          @select-category="selectCategory"
          @search="handleSearch"
          @clear-search="clearSearch"
        />
        <!-- Active filter indicator -->
        <transition name="fade">
          <div v-if="selectedCategory" class="active-filter-badge">
            <Icon name="filter" />
            <span>{{ $t('knowledge.browser.filteringBy', { category: formatCategoryName(selectedCategory) }) }}</span>
            <button
              @click="selectCategory(null)"
              class="clear-filter-btn"
              :aria-label="$t('knowledge.browser.clearCategoryFilter')"
            >
              <Icon name="times" />
            </button>
          </div>
        </transition>
      </div>

      <!-- Refresh vectorization status button (Issue #162) -->
      <BaseButton
        variant="outline-solid"
        size="sm"
        :loading="isRefreshingStatus"
        :disabled="isRefreshingStatus"
        @click="refreshVectorizationStatus"
        class="refresh-status-btn"
        :title="$t('knowledge.browser.refreshVectorizationStatus')"
      >
        <Icon name="sync-alt" v-if="!isRefreshingStatus" />
        <span>{{ $t('knowledge.browser.status') }}</span>
      </BaseButton>
    </div>

    <!-- Batch Selection Toolbar (Floating) -->
    <transition name="slide-down">
      <div v-if="hasSelection" class="batch-toolbar">
        <div class="toolbar-content">
          <div class="toolbar-info">
            <Icon name="check-square" />
            <span>{{ $t('knowledge.browser.documentsSelected', { count: selectionCount }) }}</span>
          </div>
          <div class="toolbar-actions">
            <BaseButton
              variant="primary"
              @click="vectorizeSelected"
              :disabled="!canVectorizeSelection || isVectorizing"
              :loading="isVectorizing"
              class="toolbar-btn vectorize"
            >
              <Icon name="cubes" v-if="!isVectorizing" />
              {{ $t('knowledge.browser.vectorizeSelected') }}
            </BaseButton>
            <BaseButton
              variant="secondary"
              @click="deselectAll"
              class="toolbar-btn cancel"
            >
              <Icon name="times" />
              {{ $t('knowledge.browser.clearSelection') }}
            </BaseButton>
          </div>
        </div>
      </div>
    </transition>

    <!-- Vectorization Progress Modal -->
    <VectorizationProgressModal
      :show="showProgressModal"
      :document-states="documentStates"
      @close="showProgressModal = false"
      @retry-failed="handleRetryFailed"
      @cancel="handleCancelVectorization"
    />

    <!-- Breadcrumb navigation -->
    <div v-if="selectedFile" class="breadcrumb">
      <BaseButton
        variant="ghost"
        size="sm"
        @click="clearSelection"
        class="breadcrumb-item"
        :aria-label="$t('knowledge.browser.backToRoot')"
      >
        <Icon name="home" /> {{ $t('knowledge.browser.root') }}
      </BaseButton>
      <Icon name="chevron-right" class="breadcrumb-sep" />
      <span v-for="(part, idx) in breadcrumbParts" :key="idx" class="breadcrumb-item active">
        {{ part }}
        <Icon name="chevron-right" class="breadcrumb-sep" v-if="idx < breadcrumbParts.length - 1" />
      </span>
    </div>

    <!-- Split pane layout -->
    <div class="split-pane">
      <!-- Left: Tree Navigation (30%) -->
      <div class="tree-pane">
        <div v-if="isLoading" class="loading-state">
          <Icon name="spinner" class="animate-spin" />
          <p>{{ $t('knowledge.browser.loadingFileTree') }}</p>
        </div>

        <div v-else-if="error" class="error-state">
          <Icon name="exclamation-triangle" />
          <p>{{ error?.message }}</p>
          <BaseButton
            variant="primary"
            @click="retryLoadKnowledgeTree"
            class="retry-btn"
          >
            <Icon name="redo" /> {{ $t('knowledge.browser.retryBtn') }}
          </BaseButton>
        </div>

        <div v-else class="tree-container">
          <EmptyState
            v-if="filteredTree.length === 0"
            icon="folder-open"
            :message="$t('knowledge.browser.noItemsFound')"
          />
          <TreeNodeComponent
            v-for="node in filteredTree"
            :key="node.id"
            :node="node"
            :expanded-nodes="expandedNodes"
            :selected-id="selectedFile?.id"
            :selected-documents="selectedDocuments"
            :vectorization-states="documentStates"
            @toggle="toggleNode"
            @select="selectNode"
            @toggle-select="toggleDocumentSelection"
            @vectorize="handleVectorizeDocument"
            @vectorize-folder="handleVectorizeFolder"
          />

          <!-- Load More button for cursor-based pagination (only for user knowledge modes) -->
          <div v-if="(props.mode === 'user' || props.mode === 'user-knowledge') && hasMoreEntries && !isLoadingMore" class="load-more-container">
            <BaseButton
              variant="primary"
              @click="loadMoreEntries"
              class="load-more-btn"
            >
              <Icon name="chevron-down" />
              {{ $t('knowledge.browser.loadMore') }}
            </BaseButton>
          </div>

          <div v-if="(props.mode === 'user' || props.mode === 'user-knowledge') && isLoadingMore" class="loading-more">
            <Icon name="spinner" class="animate-spin" />
            <span>{{ $t('knowledge.browser.loadingMoreEntries') }}</span>
          </div>
        </div>
      </div>

      <!-- Right: Content Viewer (70%) -->
      <KnowledgeContentViewer
        :selected-file="selectedFile"
        :content="fileContent"
        :is-loading="isLoadingContent"
        :error="contentError instanceof Error ? contentError.message : (contentError as string | null)"
        @close="clearSelection"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import type { IconName } from '@/components/ui/Icon.vue'
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useExpansion } from '@/composables/useExpansion'
import { useRouter } from 'vue-router'
import { createLogger } from '@/utils/debugUtils'
import {
  fetchMainCategories,
  fetchFactsByCategory,
  fetchEntriesPage,
  fetchFolderContents,
  fetchFactContent,
  type MainCategory,
} from '@/composables/knowledge/useKnowledgeBrowser'
import { useKnowledgeIcons } from '@/composables/knowledge/useKnowledgeIcons'
import { useKnowledgeCategories } from '@/composables/knowledge/useKnowledgeCategories'
import { useMachineKnowledge } from '@/composables/knowledge/useMachineKnowledge'
import { useManPages } from '@/composables/knowledge/useManPages'
import { formatDate, formatFileSize, formatCategoryName } from '@/utils/formatHelpers'
import { useKnowledgeVectorization } from '@/composables/useKnowledgeVectorization'
import { useLoadingState } from '@/composables/useLoadingState'
import { usePagination } from '@/composables/usePagination'
import { useDebounce } from '@/composables/useTimeout'
import TreeNodeComponent, { type TreeNode } from './TreeNodeComponent.vue'
import VectorizationProgressModal from './VectorizationProgressModal.vue'
import KnowledgeBrowserHeader from './KnowledgeBrowserHeader.vue'
import KnowledgeContentViewer from './KnowledgeContentViewer.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import KnowledgeMainCategories from './KnowledgeMainCategories.vue'

// Create scoped logger for KnowledgeBrowser
const logger = createLogger('KnowledgeBrowser')

// Domain composables (migrated from useKnowledgeBase BC shim in #5193)
const { getCategoryIcon, getFileIcon: getFileIconUtil } = useKnowledgeIcons()
const { getCategorizedFacts, buildCategoryFilterOptions } = useKnowledgeCategories()
const { refreshSystemKnowledge } = useMachineKnowledge()
const { populateAutoBotDocs } = useManPages()

const {
  documentStates,
  selectedDocuments,
  hasSelection,
  selectionCount,
  canVectorizeSelection,
  getDocumentStatus,
  toggleDocumentSelection: toggleDocSelection,
  deselectAll: deselectAllDocs,
  vectorizeDocument,
  vectorizeBatch,
  vectorizeSelected: vectorizeSelectedDocs,
  fetchBatchStatus,
  cleanup: cleanupVectorization
} = useKnowledgeVectorization()

// Router for navigation
const router = useRouter()

// Props
interface Props {
  mode?: 'user' | 'autobot' | 'autobot-documentation' | 'system-knowledge' | 'user-knowledge'
  preselectedCategory?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  mode: 'user',
  preselectedCategory: null
})

// Category interface — icon must be a registry IconName (rendered by
// KnowledgeBrowserHeader through <Icon :name>)
interface CategoryOption {
  value: string | null
  label: string
  icon: IconName
  count: number
}

// Loose shape of a knowledge fact/entry as returned by the KB endpoints
// (Record<string, unknown> at the wire; these are the fields we read).
interface KnowledgeFactLike {
  key?: string
  title?: string
  source?: string
  content?: string
  full_content?: string
  timestamp?: string
  created_at?: string
  category?: string
  metadata?: Record<string, unknown>
}

// Nested folder scaffold built while grouping facts by path segment. Each key
// is either a nested directory or the special `_files` bucket of leaf nodes.
interface NestedDir {
  _files?: TreeNode[]
  [segment: string]: NestedDir | TreeNode[] | undefined
}

// State
const treeData = ref<TreeNode[]>([])
const nodeExpansion = useExpansion<string>()
const expandedNodes = nodeExpansion.expanded
const selectedFile = ref<TreeNode | null>(null)
const fileContent = ref('')
const searchQuery = ref('')
const debouncedSearchQuery = ref('')
const updateDebouncedSearch = useDebounce((value: string) => {
  debouncedSearchQuery.value = value
}, 300)
const selectedCategory = ref<string | null>(null)
const selectedMainCategory = ref<string | null>(null)
const mainCategories = ref<MainCategory[]>([])
// Issue #5201: track backend KB connectivity so the UI can distinguish
// "empty KB" (all counts 0, kb_connected=true) from "broken KB"
// (kb_connected=false). Defaults to true so we don't flash the error
// banner before the first fetch completes.
const kbConnected = ref<boolean>(true)
// Issue #5590: track fetch-layer errors (5xx, network) separately from
// Redis-down (kb_connected=false). Prevents blaming Redis when the real
// cause is an unrelated backend error.
const kbFetchError = ref<boolean>(false)
const categoryCounts = ref<Record<string, number>>({})
const isVectorizing = ref(false)
const showProgressModal = ref(false)
const isRefreshingStatus = ref(false)  // Issue #162: Loading state for status refresh
const populationStates = ref<Record<string, { isPopulating: boolean; progress: number }>>({
  'autobot-documentation': { isPopulating: false, progress: 0 },
  'system-knowledge': { isPopulating: false, progress: 0 }
})


// Use composables for async operations
const { isLoading, wrap: loadKnowledgeTree } = useLoadingState()
const error = ref<Error | null>(null)
const { isLoading: isLoadingContent, wrap: loadFileContentOp } = useLoadingState()
const contentError = ref<Error | null>(null)

// Cursor-based pagination for user knowledge entries
const allLoadedEntries = ref<Record<string, unknown>[]>([])
const entriesCursor = ref<string>('0')
const hasMoreEntries = ref<boolean>(true)
const isLoadingMore = ref<boolean>(false)

// Fetch function for cursor-based pagination — delegates to useKnowledgeBrowser
const fetchEntries = fetchEntriesPage

// Load more entries function
const loadMore = async () => {
  if (isLoadingMore.value || !hasMoreEntries.value) return

  isLoadingMore.value = true
  try {
    const result = await fetchEntries(entriesCursor.value)
    allLoadedEntries.value = [...allLoadedEntries.value, ...result.items]
    entriesCursor.value = result.nextCursor
    hasMoreEntries.value = result.hasMore
  } catch (error) {
    logger.error('Failed to load more entries:', error)
  } finally {
    isLoadingMore.value = false
  }
}

// Reset pagination function
const resetPagination = () => {
  allLoadedEntries.value = []
  entriesCursor.value = '0'
  hasMoreEntries.value = true
  isLoadingMore.value = false
}

// Computed
const breadcrumbParts = computed(() => {
  if (!selectedFile.value) return []
  return selectedFile.value.path.split('/').filter(p => p)
})

const availableCategories = computed((): CategoryOption[] => {
  const categories: CategoryOption[] = [
    {
      value: null,
      label: 'All',
      icon: 'th-large',
      count: Object.values(categoryCounts.value).reduce((sum, count) => sum + count, 0)
    }
  ]

  // Add categories from tree data - filtered by selected main category
  const catSet = new Set<string>()
  treeData.value.forEach(node => {
    if (node.category) {
      // If a main category is selected, only show subcategories from that main category
      if (selectedMainCategory.value) {
        const catName = node.category.toLowerCase()

        const belongsToMainCat =
          (selectedMainCategory.value === 'autobot-documentation' &&
           (catName.includes('autobot') || catName.includes('documentation') || catName.includes('docs'))) ||
          (selectedMainCategory.value === 'system-knowledge' &&
           (catName.includes('man') || catName.includes('system') || catName.includes('command') ||
            catName.includes('os') || catName.includes('machine'))) ||
          (selectedMainCategory.value === 'user-knowledge' &&
           !catName.includes('autobot') && !catName.includes('documentation') && !catName.includes('docs') &&
           !catName.includes('man') && !catName.includes('system') && !catName.includes('command') &&
           !catName.includes('os') && !catName.includes('machine'))

        if (belongsToMainCat) {
          catSet.add(node.category)
        }
      } else {
        catSet.add(node.category)
      }
    }
  })

  catSet.forEach(cat => {
    categories.push({
      value: cat,
      label: formatCategoryName(cat),
      icon: getCategoryIcon(cat),
      count: categoryCounts.value[cat] || 0
    })
  })

  return categories
})

const filteredTree = computed(() => {
  let tree = treeData.value

  // Filter by main category first
  if (selectedMainCategory.value) {
    tree = tree.filter(node => {
      const catName = node.category?.toLowerCase() || ''

      if (selectedMainCategory.value === 'autobot-documentation') {
        return catName.includes('autobot') || catName.includes('documentation') || catName.includes('docs')
      } else if (selectedMainCategory.value === 'system-knowledge') {
        return catName.includes('man') || catName.includes('system') || catName.includes('command') ||
               catName.includes('os') || catName.includes('machine')
      } else if (selectedMainCategory.value === 'user-knowledge') {
        // User knowledge is anything NOT in the other two categories
        return !catName.includes('autobot') && !catName.includes('documentation') && !catName.includes('docs') &&
               !catName.includes('man') && !catName.includes('system') && !catName.includes('command') &&
               !catName.includes('os') && !catName.includes('machine')
      }
      return true
    })
  }

  // Filter by subcategory
  if (selectedCategory.value) {
    tree = tree.filter(node => node.category === selectedCategory.value)
  }

  // Filter by search query
  // Filter by search query (debounced to avoid re-rendering on every keystroke)
  if (!debouncedSearchQuery.value) return tree

  const query = debouncedSearchQuery.value.toLowerCase()

  const filterNodes = (nodes: TreeNode[]): TreeNode[] => {
    return nodes.reduce((acc: TreeNode[], node) => {
      const matches = node.name.toLowerCase().includes(query)
      const children = node.children ? filterNodes(node.children) : []

      if (matches || children.length > 0) {
        acc.push({
          ...node,
          children: children.length > 0 ? children : node.children
        })

        // Auto-expand matching folders
        if (node.type === 'folder' && (matches || children.length > 0)) {
          nodeExpansion.expand(node.id)
        }
      }

      return acc
    }, [])
  }

  return filterNodes(tree)
})

// Helper function to build nested folder structure from file paths
const buildNestedTree = (facts: Record<string, unknown>[], category: string): TreeNode[] => {
  const root: NestedDir = {};

  (facts as KnowledgeFactLike[]).forEach((fact, factIdx: number) => {
    // Extract filename from metadata
    const filename = (fact.metadata?.filename || fact.title || `Fact ${factIdx + 1}`) as string

    // Parse the path (e.g., "docs/api/endpoints.md" -> ["docs", "api", "endpoints.md"])
    const pathParts = filename.split('/').filter((p: string) => p)

    // Build nested structure
    let current = root
    for (let i = 0; i < pathParts.length; i++) {
      const part = pathParts[i]
      const isLast = i === pathParts.length - 1

      if (isLast) {
        // It's a file
        if (!current._files) current._files = []
        // Extract the actual fact ID from the Redis key (e.g., "fact:UUID" -> "UUID")
        const factId = fact.key ? fact.key.replace('fact:', '') : `fact-${category}-${factIdx}`
        const fileContent = (fact.full_content || fact.content || '') as string
        current._files.push({
          id: factId, // Use actual fact ID from Redis, not synthetic ID
          name: part,
          type: 'file' as const,
          path: `/${category}/${filename}`,
          category: category,
          size: fileContent.length,
          content: fileContent,
          metadata: {
            ...fact.metadata,
            key: fact.key,
            full_content: fact.full_content
          }
        })
      } else {
        // It's a folder
        if (!current[part]) {
          current[part] = {}
        }
        current = current[part] as NestedDir
      }
    }
  })

  // Convert nested object to TreeNode array
  const convertToTreeNodes = (obj: NestedDir, prefix = ''): TreeNode[] => {
    const nodes: TreeNode[] = []

    // Add folders
    Object.keys(obj).forEach(key => {
      if (key === '_files') return

      const folderPath = prefix ? `${prefix}/${key}` : key
      const children = convertToTreeNodes(obj[key] as NestedDir, folderPath)

      // Add files from this level
      const childFiles = (obj[key] as NestedDir)._files
      if (childFiles) {
        children.push(...childFiles)
      }

      nodes.push({
        id: `folder-${category}-${folderPath}`,
        name: key,
        type: 'folder' as const,
        path: `/${category}/${folderPath}`,
        category: category,
        children: children
      })
    })

    return nodes
  }

  const nestedNodes = convertToTreeNodes(root)

  // Add root-level files
  if (root._files) {
    nestedNodes.push(...root._files)
  }

  return nestedNodes
}

// Methods
const selectCategory = (category: string | null) => {
  selectedCategory.value = category
}

const selectMainCategory = (mainCatId: string) => {
  selectedMainCategory.value = mainCatId
  // Filter subcategories based on main category
  // This will be handled by filteredTree computed property
}

const loadMainCategories = async () => {
  kbFetchError.value = false
  try {
    const data = await fetchMainCategories()

    if (data && data.categories) {
      mainCategories.value = data.categories
      // Issue #5201: surface backend connectivity flag. Treat missing
      // field as "connected" (true) to stay compatible with older
      // backends that predate the field.
      kbConnected.value = data.kb_connected !== false
    }
  } catch (err) {
    logger.error('Failed to load main categories:', err)
    // Issue #5590: fetch failed (5xx, network error) — flag separately
    // from kb_connected=false so the UI shows a generic message rather
    // than blaming Redis for an unrelated backend error.
    kbFetchError.value = true
    // Set default categories if API fails
    mainCategories.value = [
      {
        id: 'autobot-documentation',
        name: 'AutoBot Documentation',
        description: "AutoBot's initial knowledge - documentation and guides",
        icon: 'book',
        color: '#3b82f6',
        count: 0
      },
      {
        id: 'system-knowledge',
        name: 'System Knowledge',
        description: "AutoBot's initial knowledge - system info, man pages, OS knowledge",
        icon: 'server',
        color: '#10b981',
        count: 0
      },
      {
        id: 'user-knowledge',
        name: 'User Knowledge',
        description: 'What AutoBot is used for - user-provided domain knowledge',
        icon: 'user-circle',
        color: '#f59e0b',
        count: 0
      }
    ]
  }
}


// Helper function to extract all file IDs and names from tree (Issue #162, #165)
const extractFileIdsAndNames = (nodes: TreeNode[]): { ids: string[], names: Map<string, string> } => {
  const ids: string[] = []
  const names = new Map<string, string>()
  const traverse = (nodeList: TreeNode[]) => {
    for (const node of nodeList) {
      if (node.type === 'file') {
        ids.push(node.id)
        // Issue #165: Store document name for display in vectorization modal
        names.set(node.id, node.name)
      } else if (node.children) {
        traverse(node.children)
      }
    }
  }
  traverse(nodes)
  return { ids, names }
}

// Fetch vectorization status for all files in tree (Issue #162, #165)
const fetchVectorizationStatuses = async (tree: TreeNode[]) => {
  const { ids: fileIds, names: documentNames } = extractFileIdsAndNames(tree)
  if (fileIds.length > 0) {
    logger.info(`Fetching vectorization status for ${fileIds.length} documents`)
    // Issue #165: Pass document names to fetchBatchStatus for display
    await fetchBatchStatus(fileIds, documentNames)
  }
}

// Manual refresh of vectorization status (Issue #162)
const refreshVectorizationStatus = async () => {
  if (isRefreshingStatus.value) return
  isRefreshingStatus.value = true
  try {
    await fetchVectorizationStatuses(treeData.value)
    logger.info('Vectorization status refreshed')
  } catch (error) {
    logger.error('Failed to refresh vectorization status:', error)
  } finally {
    isRefreshingStatus.value = false
  }
}

// Load main knowledge tree with useLoadingState wrapper
const retryLoadKnowledgeTree = () => {
  error.value = null
  loadKnowledgeTree(loadKnowledgeTreeFn).catch(err => {
    error.value = err instanceof Error ? err : new Error(String(err))
  })
}

const loadKnowledgeTreeFn = async () => {
  // Load facts from knowledge base by category
  const data = await fetchFactsByCategory()

  if (data && data.categories) {
    // Build tree structure from categories
    const categoriesByName = data.categories as Record<string, Record<string, unknown>[]>
    const categories = Object.keys(categoriesByName)

    // Update category counts
    const counts: Record<string, number> = {}
    categories.forEach(cat => {
      counts[cat] = categoriesByName[cat].length
    })
    categoryCounts.value = counts

    treeData.value = categories.map((category: string, idx: number) => {
      const facts = categoriesByName[category] || []

      // Build nested folder structure based on file paths
      const children = buildNestedTree(facts, category)

      return {
        id: `folder-${idx}`,
        name: formatCategoryName(category),
        type: 'folder' as const,
        path: `/${category}`,
        category: category,
        children: children
      }
    })

    // Issue #162: Fetch vectorization status for all files after tree is built
    await fetchVectorizationStatuses(treeData.value)
  }
}

const loadUserKnowledge = async () => {
  // Reset pagination and load first page
  resetPagination()
  await loadMore()
  // Build tree from loaded entries
  buildTreeFromEntries(allLoadedEntries.value)
}

const loadMoreEntries = async () => {
  // Save expanded paths before rebuild to preserve tree state
  const expandedPaths = getExpandedPaths(treeData.value, expandedNodes.value)

  await loadMore()
  // Rebuild tree with all accumulated entries
  buildTreeFromEntries(allLoadedEntries.value)

  // Restore expanded state after rebuild
  restoreExpandedState(treeData.value, expandedPaths)
}

const buildTreeFromEntries = (entries: Record<string, unknown>[]) => {
  // Build tree from entries (group by category)
  const categoryMap = new Map<string, TreeNode[]>()

  if (Array.isArray(entries)) {
    (entries as KnowledgeFactLike[]).forEach((entry, idx: number) => {
      const category = entry.category || 'Uncategorized'

      if (!categoryMap.has(category)) {
        categoryMap.set(category, [])
      }

      categoryMap.get(category)?.push({
        id: `file-${idx}`,
        name: entry.title || entry.source || `Entry ${idx + 1}`,
        type: 'file',
        path: `/${category}/${entry.title || entry.source}`,
        size: entry.content?.length || 0,
        date: entry.timestamp || entry.created_at,
        category: category,
        metadata: entry
      })
    })
  }

  // Update category counts
  const counts: Record<string, number> = {}
  categoryMap.forEach((files, category) => {
    counts[category] = files.length
  })
  categoryCounts.value = counts

  // Convert to tree structure
  treeData.value = Array.from(categoryMap.entries()).map(([category, files], idx) => ({
    id: `folder-${idx}`,
    name: formatCategoryName(category),
    type: 'folder' as const,
    path: `/${category}`,
    category: category,
    children: files
  }))
}

const toggleNode = (nodeId: string) => {
  const wasExpanded = nodeExpansion.isExpanded(nodeId)
  nodeExpansion.toggle(nodeId)
  if (!wasExpanded) {
    // Load folder contents if not already loaded
    const node = findNode(treeData.value, nodeId)
    if (node && node.type === 'folder' && (!node.children || node.children.length === 0)) {
      loadFolderContents(node)
    }
  }
}

const selectNode = async (node: TreeNode) => {
  if (node.type === 'file') {
    selectedFile.value = node
    await loadFileContent(node)
  } else {
    toggleNode(node.id)
  }
}

const toggleDocumentSelection = (documentId: string) => {
  toggleDocSelection(documentId)
}

const deselectAll = () => {
  deselectAllDocs()
}

const handleVectorizeDocument = async (documentId: string) => {
  isVectorizing.value = true
  try {
    await vectorizeDocument(documentId)
    // Show success notification
    logger.info(`Document ${documentId} vectorized successfully`)
  } catch (error) {
    logger.error('Vectorization failed:', error)
  } finally {
    isVectorizing.value = false
  }
}

const handleVectorizeFolder = async (folderNode: TreeNode) => {
  // Recursively collect all unvectorized file IDs from this folder
  const collectUnvectorizedFiles = (node: TreeNode): string[] => {
    const fileIds: string[] = []

    if (node.type === 'file') {
      // Check if file is not vectorized
      const state = documentStates.value.get(node.id)
      const status = state?.status || getDocumentStatus(node.id)
      if (status !== 'vectorized') {
        fileIds.push(node.id)
      }
    } else if (node.type === 'folder' && node.children) {
      // Recursively collect from children
      node.children.forEach(child => {
        fileIds.push(...collectUnvectorizedFiles(child))
      })
    }

    return fileIds
  }

  const documentIds = collectUnvectorizedFiles(folderNode)

  if (documentIds.length === 0) {
    logger.info('No unvectorized documents found in this folder')
    return
  }

  logger.info(`Starting batch vectorization for ${documentIds.length} documents in folder: ${folderNode.name}`)

  isVectorizing.value = true
  showProgressModal.value = true

  try {
    const result = await vectorizeBatch(documentIds)
    logger.info('Folder vectorization complete:', result)
    // Modal stays open to show results
  } catch (error) {
    logger.error('Folder vectorization failed:', error)
  } finally {
    isVectorizing.value = false
  }
}

const vectorizeSelected = async () => {
  isVectorizing.value = true
  showProgressModal.value = true // Show progress modal
  try {
    const result = await vectorizeSelectedDocs()
    logger.info('Batch vectorization complete:', result)
    // Keep modal open to show results
  } catch (error) {
    logger.error('Batch vectorization failed:', error)
  } finally {
    isVectorizing.value = false
  }
}

const handleRetryFailed = async () => {
  // Get all failed document IDs
  const failedDocs = Array.from(documentStates.value.entries())
    .filter(([_, state]) => state.status === 'failed')
    .map(([id, _]) => id)

  if (failedDocs.length > 0) {
    isVectorizing.value = true
    // Retry all failed documents in parallel - eliminates N+1 sequential calls
    const results = await Promise.allSettled(
      failedDocs.map(docId => vectorizeDocument(docId))
    )
    // Log any failures
    results.forEach((result, index) => {
      if (result.status === 'rejected') {
        logger.error(`Failed to retry vectorization for ${failedDocs[index]}:`, result.reason)
      }
    })
    isVectorizing.value = false
  }
}

const handleCancelVectorization = () => {
  // Stop ongoing vectorization
  isVectorizing.value = false
  showProgressModal.value = false
  // Note: Actual cancellation of backend jobs would need additional backend support
  logger.info('Vectorization cancelled by user')
}

const handlePopulate = async (categoryId: string) => {
  if (populationStates.value[categoryId]?.isPopulating) return

  populationStates.value[categoryId] = { isPopulating: true, progress: 0 }

  try {
    let result
    if (categoryId === 'autobot-documentation') {
      result = await populateAutoBotDocs()
    } else if (categoryId === 'system-knowledge') {
      result = await refreshSystemKnowledge()
    }

    // Simulate progress updates (since backend doesn't provide real-time progress)
    const progressInterval = setInterval(() => {
      if (populationStates.value[categoryId].progress < 90) {
        populationStates.value[categoryId].progress += 10
      }
    }, 500)

    // Wait for result (assuming it takes some time)
    await new Promise(resolve => setTimeout(resolve, 3000))

    clearInterval(progressInterval)
    populationStates.value[categoryId].progress = 100

    // Show success for a moment
    await new Promise(resolve => setTimeout(resolve, 1000))

    // Reset state
    populationStates.value[categoryId] = { isPopulating: false, progress: 0 }

    // Reload the knowledge tree to show new items
    error.value = null
    await loadKnowledgeTree(loadKnowledgeTreeFn).catch(err => {
      error.value = err instanceof Error ? err : new Error(String(err))
    })

    logger.info(`${categoryId} population completed:`, result)
  } catch (error) {
    logger.error(`Failed to populate ${categoryId}:`, error)
    populationStates.value[categoryId] = { isPopulating: false, progress: 0 }
  }
}

const handleImport = () => {
  router.push('/knowledge/upload')
}

const loadFolderContents = async (folder: TreeNode) => {
  try {
    const data = await fetchFolderContents(folder.category || '')

    if (data.results && Array.isArray(data.results)) {
      folder.children = (data.results as KnowledgeFactLike[]).map((item, idx: number) => ({
        id: `file-${folder.id}-${idx}`,
        name: (item.metadata?.title || item.metadata?.source || `Document ${idx + 1}`) as string,
        type: 'file' as const,
        path: `${folder.path}/${item.metadata?.title || item.metadata?.source}`,
        size: (item.content?.length as number | undefined) || 0,
        date: item.metadata?.timestamp as string | undefined,
        category: folder.category,
        metadata: item
      }))
    }
  } catch (err: unknown) {
    logger.error('Failed to load folder contents:', err)
  }
}

const loadFileContent = async (file: TreeNode) => {
  contentError.value = null
  await loadFileContentOp(async () => {
    // First check if we have full_content in metadata
    if (file.metadata?.full_content) {
      fileContent.value = file.metadata.full_content
    } else if (file.content && !file.content.endsWith('...')) {
      // Use content if it's not truncated
      fileContent.value = file.content
    } else {
      // Need to fetch full content from Redis
      // Extract fact_id from the key (e.g., "fact:uuid" -> "uuid")
      const factKey = file.metadata?.key || file.path?.split('/').pop()

      if (factKey) {
        // Fetch full fact data from backend
        const response = await fetchFactContent(factKey)

        if (response && response.content) {
          fileContent.value = response.content
        } else {
          fileContent.value = file.content || 'Content not available'
        }
      } else {
        fileContent.value = file.content || 'Content not available'
      }
    }
  }).catch(err => {
    contentError.value = err instanceof Error ? err : new Error(String(err))
  })
  // Update size to reflect actual loaded content length
  if (selectedFile.value && fileContent.value) {
    selectedFile.value.size = fileContent.value.length
  }
}

const findNode = (nodes: TreeNode[], id: string): TreeNode | null => {
  for (const node of nodes) {
    if (node.id === id) return node
    if (node.children) {
      const found = findNode(node.children, id)
      if (found) return found
    }
  }
  return null
}

// Helper to collect paths of expanded nodes before tree rebuild
const getExpandedPaths = (nodes: TreeNode[], expandedNodeIds: Set<string>): Set<string> => {
  const paths = new Set<string>()

  const collectPaths = (nodes: TreeNode[]) => {
    for (const node of nodes) {
      if (expandedNodeIds.has(node.id)) {
        paths.add(node.path)
      }
      if (node.children) {
        collectPaths(node.children)
      }
    }
  }

  collectPaths(nodes)
  return paths
}

// Helper to restore expanded state from paths after tree rebuild
const restoreExpandedState = (nodes: TreeNode[], expandedPaths: Set<string>) => {
  const newExpandedIds = new Set<string>()

  const restorePaths = (nodes: TreeNode[]) => {
    for (const node of nodes) {
      if (expandedPaths.has(node.path)) {
        newExpandedIds.add(node.id)
      }
      if (node.children) {
        restorePaths(node.children)
      }
    }
  }

  restorePaths(nodes)
  nodeExpansion.expandAll(newExpandedIds)
}

const clearSelection = () => {
  selectedFile.value = null
  fileContent.value = ''
  contentError.value = null
}

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

// Utility functions (now using composable)
const getFileIcon = (node: TreeNode): string => {
  if (node.type === 'folder') {
    return nodeExpansion.isExpanded(node.id) ? 'folder-open' : 'folder'
  }

  return getFileIconUtil(node.name, false)
}

// Lifecycle
onMounted(() => {
  loadMainCategories()
  error.value = null
  loadKnowledgeTree(loadKnowledgeTreeFn).catch(err => {
    error.value = err instanceof Error ? err : new Error(String(err))
  })

  // Set preselected category from props
  if (props.preselectedCategory) {
    selectedMainCategory.value = props.preselectedCategory
  }
})

onUnmounted(() => {
  cleanupVectorization()
})

// Watch mode changes
watch(() => props.mode, () => {
  // Reset pagination state when switching modes
  resetPagination()
  error.value = null
  loadKnowledgeTree(loadKnowledgeTreeFn).catch(err => {
    error.value = err instanceof Error ? err : new Error(String(err))
  })
  clearSelection()
  nodeExpansion.collapseAll()
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.knowledge-file-browser {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-secondary);
}

/* Header */
.browser-header {
  background: var(--bg-card);
  padding: var(--spacing-4);
  border-bottom: 2px solid var(--border-default);
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  flex-wrap: wrap;
}

/* Category Filter Container (Issue #161) */
.category-tabs-container {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
  flex: 1;
  min-width: 0;
}

/* Category Tabs */
.category-tabs {
  display: flex;
  gap: var(--spacing-2);
  overflow-x: auto;
  flex: 0 0 auto;
  padding-bottom: var(--spacing-1);
  scrollbar-width: thin;
  scrollbar-color: var(--color-primary-alpha-30) transparent;
}

.category-tabs::-webkit-scrollbar {
  height: 4px;
}

.category-tabs::-webkit-scrollbar-track {
  background: transparent;
}

.category-tabs::-webkit-scrollbar-thumb {
  background: var(--color-primary-alpha-30);
  border-radius: var(--radius-xs);
}

.category-tab {
  white-space: nowrap;
  transition: all var(--duration-250) var(--ease-in-out);
  position: relative;
}

.category-tab-active {
  box-shadow: 0 2px 8px var(--color-primary-alpha-30);
}

.category-tab-icon {
  margin-right: var(--spacing-1);
  transition: transform var(--duration-200) var(--ease-out);
}

.category-tab:hover .category-tab-icon {
  transform: scale(1.1);
}

.category-tab-label {
  transition: color var(--duration-200) var(--ease-out);
}

.category-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.5rem;
  height: 1.25rem;
  padding: var(--spacing-0) var(--spacing-1-5);
  background: rgba(0, 0, 0, 0.1);
  border-radius: var(--radius-xl);
  font-size: var(--text-xs);
  font-weight: 600;
  margin-left: var(--spacing-1-5);
  transition: all var(--duration-200) var(--ease-out);
}

.category-count-active {
  background: rgba(255, 255, 255, 0.3);
}

/* Active filter badge (Issue #161) */
.active-filter-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-1-5) var(--spacing-3);
  background: var(--color-primary-bg);
  border: 1px solid var(--color-primary-light);
  border-radius: var(--radius-2xl);
  font-size: 0.8125rem;
  color: var(--color-primary-dark);
  font-weight: 500;
  width: fit-content;
}

.active-filter-badge i.fa-filter {
  color: var(--color-primary);
  font-size: var(--text-xs);
}

.clear-filter-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.25rem;
  height: 1.25rem;
  padding: var(--spacing-0);
  background: transparent;
  border: none;
  border-radius: 50%;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all var(--duration-200) var(--ease-out);
}

.clear-filter-btn:hover {
  background: var(--color-error-alpha-10);
  color: var(--color-error);
}

/* Category tab transitions */
.category-tab-enter-active,
.category-tab-leave-active {
  transition: all var(--duration-300) var(--ease-out);
}

.category-tab-enter-from {
  opacity: 0;
  transform: translateY(-10px);
}

.category-tab-leave-to {
  opacity: 0;
  transform: translateY(10px);
}

.category-tab-move {
  transition: transform var(--duration-300) var(--ease-out);
}

/* Fade transition for filter badge */
.fade-enter-active,
.fade-leave-active {
  transition: opacity var(--duration-200) var(--ease-out), transform var(--duration-200) var(--ease-out);
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(-5px);
}

/* Refresh status button (Issue #162) */
.refresh-status-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  white-space: nowrap;
  flex-shrink: 0;
}

.refresh-status-btn i {
  font-size: var(--text-sm);
}

/* Batch Toolbar */
.batch-toolbar {
  position: sticky;
  top: 0;
  z-index: 100;
  background: var(--color-primary);
  box-shadow: 0 4px 12px var(--color-primary-alpha-30);
  padding: var(--spacing-3) var(--spacing-6);
  border-bottom: 1px solid rgba(255, 255, 255, 0.2);
}

.toolbar-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  max-width: 1200px;
  margin: 0 auto;
}

.toolbar-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  color: var(--bg-card);
  font-weight: 500;
}

.toolbar-info i {
  font-size: var(--text-xl);
}

.toolbar-actions {
  display: flex;
  gap: var(--spacing-3);
}

/* Toolbar button custom styling */
.toolbar-btn.vectorize {
  background: var(--bg-card);
  color: var(--color-primary);
}

.toolbar-btn.cancel {
  background: rgba(255, 255, 255, 0.2);
  color: var(--bg-card);
  border: 1px solid rgba(255, 255, 255, 0.3);
}

.slide-down-enter-active,
.slide-down-leave-active {
  transition: all var(--duration-300) var(--ease-out);
}

.slide-down-enter-from,
.slide-down-leave-to {
  transform: translateY(-100%);
  opacity: 0;
}

/* Search Bar */
.search-bar {
  position: relative;
  display: flex;
  align-items: center;
  flex: 1 1 300px;
  max-width: 500px;
  min-width: 200px;
}

.search-bar i.fa-search {
  position: absolute;
  left: 1rem;
  color: var(--text-muted);
}

.search-input {
  width: 100%;
  padding: var(--spacing-2-5) var(--spacing-10) var(--spacing-2-5) var(--spacing-10);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  transition: all var(--duration-200);
}

.search-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-alpha-10);
}
.search-input:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.clear-btn {
  position: absolute;
  right: 0.5rem;
}

/* Breadcrumb */
.breadcrumb {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-6);
  background: var(--bg-card);
  border-bottom: 1px solid var(--border-default);
  font-size: var(--text-sm);
}

.breadcrumb-item.active {
  color: var(--text-primary);
  cursor: default;
}

.breadcrumb-sep {
  color: var(--border-light);
  font-size: var(--text-xs);
}

/* Split pane layout */
.split-pane {
  display: grid;
  grid-template-columns: 30% 70%;
  flex: 1;
  overflow: hidden;
  gap: var(--spacing-0);
}

.tree-pane {
  background: var(--bg-card);
  border-right: 2px solid var(--border-default);
  overflow-y: auto;
  overflow-x: hidden;
}

.content-pane {
  background: var(--bg-secondary);
  overflow-y: auto;
}

/* Tree container */
.tree-container {
  padding: var(--spacing-2);
}

/* Load More button container */
.load-more-container {
  display: flex;
  justify-content: center;
  padding: var(--spacing-4);
  margin-top: var(--spacing-2);
}

.loading-more {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  padding: var(--spacing-4);
  color: var(--text-tertiary);
  font-size: var(--text-sm);
}

.loading-more i {
  font-size: var(--text-base);
}

/* States */
.loading-state,
.error-state,
.placeholder-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-12) var(--spacing-6);
  text-align: center;
  color: var(--text-tertiary);
}

.loading-state i,
.error-state i,
.placeholder-state i {
  font-size: var(--text-5xl);
  margin-bottom: var(--spacing-4);
  opacity: 0.5;
}

.error-state {
  color: var(--color-error);
}

.retry-btn {
  margin-top: var(--spacing-4);
}

/* File viewer */
.file-viewer {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.file-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: var(--spacing-6);
  background: var(--bg-card);
  border-bottom: 2px solid var(--border-default);
}

.file-info {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-4);
  flex: 1;
}

.file-info > i {
  font-size: 2rem;
  color: var(--color-primary);
  margin-top: var(--spacing-1);
}

.file-info h4 {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-1);
}

.file-meta {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.close-btn {
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
}

.file-content {
  flex: 1;
  overflow-y: auto;
  background: var(--bg-card);
  margin: var(--spacing-4);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
}

.loading-content,
.error-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-12);
  color: var(--text-tertiary);
}

.error-content {
  color: var(--color-error);
}

.content-display {
  padding: var(--spacing-6);
  font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
  font-size: var(--text-sm);
  line-height: 1.6;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-wrap: break-word;
  margin: var(--spacing-0);
}

/* Scrollbar styling */
.tree-pane::-webkit-scrollbar,
.content-pane::-webkit-scrollbar {
  width: 8px;
}

.tree-pane::-webkit-scrollbar-track,
.content-pane::-webkit-scrollbar-track {
  background: var(--bg-tertiary);
}

.tree-pane::-webkit-scrollbar-thumb,
.content-pane::-webkit-scrollbar-thumb {
  background: var(--border-secondary);
  border-radius: var(--radius-default);
}

.tree-pane::-webkit-scrollbar-thumb:hover,
.content-pane::-webkit-scrollbar-thumb:hover {
  background: var(--border-secondary);
}
</style>
