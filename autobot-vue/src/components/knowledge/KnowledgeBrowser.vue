<template>
  <div class="knowledge-file-browser">
    <!-- Main Categories -->
    <div class="main-categories">
      <div
        v-for="mainCat in mainCategories"
        :key="mainCat.id"
        class="main-category-card"
        :style="{ borderColor: mainCat.color }"
        @click="selectMainCategory(mainCat.id)"
      >
        <div class="category-icon" :style="{ backgroundColor: mainCat.color }">
          <i :class="mainCat.icon"></i>
        </div>
        <div class="category-info">
          <h3>{{ mainCat.name }}</h3>
          <p>{{ mainCat.description }}</p>
          <div class="category-stats">
            <span class="fact-count">{{ mainCat.count }} facts</span>
            <BaseButton
              v-if="mainCat.id !== 'user-knowledge'"
              variant="primary"
              size="sm"
              :loading="populationStates[mainCat.id]?.isPopulating"
              :disabled="populationStates[mainCat.id]?.isPopulating"
              @click.stop="handlePopulate(mainCat.id)"
              class="populate-btn"
            >
              <i v-if="!populationStates[mainCat.id]?.isPopulating" class="fas fa-sync"></i>
              <span v-if="!populationStates[mainCat.id]?.isPopulating">Populate</span>
              <span v-else>{{ populationStates[mainCat.id]?.progress || 0 }}%</span>
            </BaseButton>
          </div>
        </div>
      </div>
    </div>

    <!-- Header -->
    <div class="browser-header">
      <!-- Category Filter Tabs -->
      <div class="category-tabs">
        <BaseButton
          v-for="cat in availableCategories"
          :key="cat.value ?? 'all'"
          :variant="selectedCategory === cat.value ? 'primary' : 'outline'"
          size="sm"
          @click="selectCategory(cat.value)"
          class="category-tab"
        >
          <i :class="cat.icon"></i>
          {{ cat.label }}
          <span v-if="cat.count > 0" class="category-count">{{ cat.count }}</span>
        </BaseButton>
      </div>

      <!-- Search bar -->
      <div class="search-bar">
        <i class="fas fa-search"></i>
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Search files and folders..."
          class="search-input"
          @input="handleSearch"
        />
        <BaseButton
          v-if="searchQuery"
          variant="ghost"
          size="xs"
          @click="clearSearch"
          class="clear-btn"
          aria-label="Clear search"
        >
          <i class="fas fa-times"></i>
        </BaseButton>
      </div>
    </div>

    <!-- Batch Selection Toolbar (Floating) -->
    <transition name="slide-down">
      <div v-if="hasSelection" class="batch-toolbar">
        <div class="toolbar-content">
          <div class="toolbar-info">
            <i class="fas fa-check-square"></i>
            <span>{{ selectionCount }} document{{ selectionCount > 1 ? 's' : '' }} selected</span>
          </div>
          <div class="toolbar-actions">
            <BaseButton
              variant="primary"
              @click="vectorizeSelected"
              :disabled="!canVectorizeSelection || isVectorizing"
              :loading="isVectorizing"
              class="toolbar-btn vectorize"
            >
              <i v-if="!isVectorizing" class="fas fa-cubes"></i>
              Vectorize Selected
            </BaseButton>
            <BaseButton
              variant="secondary"
              @click="deselectAll"
              class="toolbar-btn cancel"
            >
              <i class="fas fa-times"></i>
              Clear Selection
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
        aria-label="Back to root"
      >
        <i class="fas fa-home"></i> Root
      </BaseButton>
      <i class="fas fa-chevron-right breadcrumb-sep"></i>
      <span v-for="(part, idx) in breadcrumbParts" :key="idx" class="breadcrumb-item active">
        {{ part }}
        <i v-if="idx < breadcrumbParts.length - 1" class="fas fa-chevron-right breadcrumb-sep"></i>
      </span>
    </div>

    <!-- Split pane layout -->
    <div class="split-pane">
      <!-- Left: Tree Navigation (30%) -->
      <div class="tree-pane">
        <div v-if="isLoading" class="loading-state">
          <i class="fas fa-spinner fa-spin"></i>
          <p>Loading file tree...</p>
        </div>

        <div v-else-if="error" class="error-state">
          <i class="fas fa-exclamation-triangle"></i>
          <p>{{ error }}</p>
          <BaseButton
            variant="primary"
            @click="loadKnowledgeTree"
            class="retry-btn"
          >
            <i class="fas fa-redo"></i> Retry
          </BaseButton>
        </div>

        <div v-else class="tree-container">
          <EmptyState
            v-if="filteredTree.length === 0"
            icon="fas fa-folder-open"
            message="No items found"
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

          <!-- Load More button for cursor-based pagination -->
          <div v-if="hasMoreEntries && !isLoadingMore" class="load-more-container">
            <BaseButton
              variant="primary"
              @click="loadMoreEntries"
              class="load-more-btn"
            >
              <i class="fas fa-chevron-down"></i>
              Load More
            </BaseButton>
          </div>

          <div v-if="isLoadingMore" class="loading-more">
            <i class="fas fa-spinner fa-spin"></i>
            <span>Loading more entries...</span>
          </div>
        </div>
      </div>

      <!-- Right: Content Viewer (70%) -->
      <div class="content-pane">
        <div v-if="!selectedFile" class="placeholder-state">
          <i class="fas fa-file-alt"></i>
          <h4>No file selected</h4>
          <p>Select a file from the tree to view its contents</p>
        </div>

        <div v-else class="file-viewer">
          <div class="file-header">
            <div class="file-info">
              <i :class="getFileIcon(selectedFile)"></i>
              <div>
                <h4>{{ selectedFile.name }}</h4>
                <p class="file-meta">
                  {{ selectedFile.type }} • {{ formatFileSize(selectedFile.size) }}
                  <span v-if="selectedFile.date"> • {{ formatDate(selectedFile.date) }}</span>
                </p>
              </div>
            </div>
            <BaseButton
              variant="ghost"
              size="sm"
              @click="clearSelection"
              class="close-btn"
              aria-label="Close file viewer"
            >
              <i class="fas fa-times"></i>
            </BaseButton>
          </div>

          <div class="file-content">
            <div v-if="isLoadingContent" class="loading-content">
              <i class="fas fa-spinner fa-spin"></i>
              <p>Loading content...</p>
            </div>

            <div v-else-if="contentError" class="error-content">
              <i class="fas fa-exclamation-circle"></i>
              <p>{{ contentError }}</p>
            </div>

            <pre v-else class="content-display">{{ fileContent }}</pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import apiClient from '@/utils/ApiClient'
import { parseApiResponse } from '@/utils/apiResponseHelpers'
import { useKnowledgeBase } from '@/composables/useKnowledgeBase'
import { useKnowledgeVectorization } from '@/composables/useKnowledgeVectorization'
import TreeNodeComponent, { type TreeNode } from './TreeNodeComponent.vue'
import VectorizationProgressModal from './VectorizationProgressModal.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import BaseButton from '@/components/base/BaseButton.vue'

// Use the shared composables
const {
  formatCategoryName,
  getFileIcon: getFileIconUtil,
  formatFileSize,
  formatDateOnly: formatDate,
  getCategoryIcon,
  populateAutoBotDocs,
  refreshSystemKnowledge
} = useKnowledgeBase()

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
  cleanup: cleanupVectorization
} = useKnowledgeVectorization()

// Props
interface Props {
  mode?: 'user' | 'autobot' | 'autobot-documentation' | 'system-knowledge' | 'user-knowledge'
  preselectedCategory?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  mode: 'user',
  preselectedCategory: null
})

// Category interface
interface CategoryOption {
  value: string | null
  label: string
  icon: string
  count: number
}

// State
const isLoading = ref(false)
const error = ref<string | null>(null)
const treeData = ref<TreeNode[]>([])
const expandedNodes = ref<Set<string>>(new Set())
const selectedFile = ref<TreeNode | null>(null)
const fileContent = ref('')
const isLoadingContent = ref(false)
const contentError = ref<string | null>(null)
const searchQuery = ref('')
const selectedCategory = ref<string | null>(null)
const selectedMainCategory = ref<string | null>(null)
const mainCategories = ref<any[]>([])
const categoryCounts = ref<Record<string, number>>({})
const isVectorizing = ref(false)
const showProgressModal = ref(false)
const populationStates = ref<Record<string, { isPopulating: boolean; progress: number }>>({
  'autobot-documentation': { isPopulating: false, progress: 0 },
  'system-knowledge': { isPopulating: false, progress: 0 }
})

// Cursor-based pagination state
const entriesCursor = ref<string>('0')
const hasMoreEntries = ref<boolean>(false)
const isLoadingMore = ref<boolean>(false)
const allLoadedEntries = ref<any[]>([])

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
      icon: 'fas fa-th-large',
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
  if (!searchQuery.value) return tree

  const query = searchQuery.value.toLowerCase()

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
          expandedNodes.value.add(node.id)
        }
      }

      return acc
    }, [])
  }

  return filterNodes(tree)
})

// Helper function to build nested folder structure from file paths
const buildNestedTree = (facts: any[], category: string): TreeNode[] => {
  const root: Record<string, any> = {}

  facts.forEach((fact: any, factIdx: number) => {
    // Extract filename from metadata
    const filename = fact.metadata?.filename || fact.title || `Fact ${factIdx + 1}`

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
        current._files.push({
          id: factId, // Use actual fact ID from Redis, not synthetic ID
          name: part,
          type: 'file' as const,
          path: `/${category}/${filename}`,
          category: category,
          content: fact.full_content || fact.content,
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
        current = current[part]
      }
    }
  })

  // Convert nested object to TreeNode array
  const convertToTreeNodes = (obj: Record<string, any>, prefix = ''): TreeNode[] => {
    const nodes: TreeNode[] = []

    // Add folders
    Object.keys(obj).forEach(key => {
      if (key === '_files') return

      const folderPath = prefix ? `${prefix}/${key}` : key
      const children = convertToTreeNodes(obj[key], folderPath)

      // Add files from this level
      if (obj[key]._files) {
        children.push(...obj[key]._files)
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
  try {
    const response = await apiClient.get('/api/knowledge_base/categories/main')
    const data = await parseApiResponse(response)

    if (data && data.categories) {
      mainCategories.value = data.categories
    }
  } catch (err) {
    console.error('Failed to load main categories:', err)
    // Set default categories if API fails
    mainCategories.value = [
      {
        id: 'autobot-documentation',
        name: 'AutoBot Documentation',
        description: "AutoBot's initial knowledge - documentation and guides",
        icon: 'fas fa-book',
        color: '#3b82f6',
        count: 0
      },
      {
        id: 'system-knowledge',
        name: 'System Knowledge',
        description: "AutoBot's initial knowledge - system info, man pages, OS knowledge",
        icon: 'fas fa-server',
        color: '#10b981',
        count: 0
      },
      {
        id: 'user-knowledge',
        name: 'User Knowledge',
        description: 'What AutoBot is used for - user-provided domain knowledge',
        icon: 'fas fa-user-circle',
        color: '#f59e0b',
        count: 0
      }
    ]
  }
}

const loadKnowledgeTree = async () => {
  isLoading.value = true
  error.value = null

  try {
    // Load facts from knowledge base by category
    const response = await apiClient.get('/api/knowledge_base/facts/by_category')
    const data = await parseApiResponse(response)

    if (data && data.categories) {
      // Build tree structure from categories
      const categories = Object.keys(data.categories)

      // Update category counts
      const counts: Record<string, number> = {}
      categories.forEach(cat => {
        counts[cat] = data.categories[cat].length
      })
      categoryCounts.value = counts

      treeData.value = categories.map((category: string, idx: number) => {
        const facts = data.categories[category] || []

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
    }
  } catch (err: any) {
    console.error('Failed to load knowledge tree:', err)
    error.value = err.message || 'Failed to load knowledge base'
  } finally {
    isLoading.value = false
  }
}

const loadUserKnowledge = async () => {
  try {
    // Reset cursor and accumulated entries for fresh load
    entriesCursor.value = '0'
    allLoadedEntries.value = []

    // Build initial query parameters
    const params = new URLSearchParams({
      limit: '100',
      cursor: entriesCursor.value
    })

    // apiClient.get() already returns parsed JSON, not a Response object
    const response = await apiClient.get(`/api/knowledge_base/entries?${params}`)
    const data = await parseApiResponse(response)

    // Handle both old (offset) and new (cursor) response formats for backward compatibility
    let entries: any[] = []
    let nextCursor = '0'
    let hasMore = false

    if (data.next_cursor !== undefined) {
      // New cursor-based format
      entries = data.entries || []
      nextCursor = data.next_cursor || '0'
      hasMore = data.has_more || false
    } else if (data.offset !== undefined) {
      // Old offset-based format (backward compatibility)
      entries = data.entries || []
      const total = data.total || 0
      const currentOffset = data.offset || 0
      hasMore = (currentOffset + entries.length) < total
      nextCursor = hasMore ? String(currentOffset + entries.length) : '0'
    } else {
      // Fallback: just entries
      entries = data.entries || []
      hasMore = false
      nextCursor = '0'
    }

    // Update cursor state
    entriesCursor.value = nextCursor
    hasMoreEntries.value = hasMore
    allLoadedEntries.value = entries

    // Build tree from entries (group by category)
    buildTreeFromEntries(allLoadedEntries.value)
  } catch (err: any) {
    console.error('Failed to load user knowledge:', err)
    error.value = err.message || 'Failed to load user knowledge'
  }
}

const loadMoreEntries = async () => {
  if (!hasMoreEntries.value || isLoadingMore.value) {
    return
  }

  isLoadingMore.value = true

  try {
    const params = new URLSearchParams({
      limit: '100',
      cursor: entriesCursor.value
    })

    const response = await apiClient.get(`/api/knowledge_base/entries?${params}`)
    const data = await parseApiResponse(response)

    // Handle response format
    let entries: any[] = []
    let nextCursor = '0'
    let hasMore = false

    if (data.next_cursor !== undefined) {
      // New cursor-based format
      entries = data.entries || []
      nextCursor = data.next_cursor || '0'
      hasMore = data.has_more || false
    } else if (data.offset !== undefined) {
      // Old offset-based format (backward compatibility)
      entries = data.entries || []
      const total = data.total || 0
      const currentOffset = data.offset || 0
      hasMore = (currentOffset + entries.length) < total
      nextCursor = hasMore ? String(currentOffset + entries.length) : '0'
    } else {
      entries = data.entries || []
      hasMore = false
      nextCursor = '0'
    }

    // Update cursor state
    entriesCursor.value = nextCursor
    hasMoreEntries.value = hasMore

    // Append new entries to existing ones
    allLoadedEntries.value = [...allLoadedEntries.value, ...entries]

    // Rebuild tree with all accumulated entries
    buildTreeFromEntries(allLoadedEntries.value)
  } catch (err: any) {
    console.error('Failed to load more entries:', err)
    error.value = err.message || 'Failed to load more entries'
  } finally {
    isLoadingMore.value = false
  }
}

const buildTreeFromEntries = (entries: any[]) => {
  // Build tree from entries (group by category)
  const categoryMap = new Map<string, TreeNode[]>()

  if (Array.isArray(entries)) {
    entries.forEach((entry: any, idx: number) => {
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
  if (expandedNodes.value.has(nodeId)) {
    expandedNodes.value.delete(nodeId)
  } else {
    expandedNodes.value.add(nodeId)

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
    console.log(`Document ${documentId} vectorized successfully`)
  } catch (error) {
    console.error('Vectorization failed:', error)
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
    console.log('No unvectorized documents found in this folder')
    return
  }

  console.log(`Starting batch vectorization for ${documentIds.length} documents in folder: ${folderNode.name}`)

  isVectorizing.value = true
  showProgressModal.value = true

  try {
    const result = await vectorizeBatch(documentIds)
    console.log('Folder vectorization complete:', result)
    // Modal stays open to show results
  } catch (error) {
    console.error('Folder vectorization failed:', error)
  } finally {
    isVectorizing.value = false
  }
}

const vectorizeSelected = async () => {
  isVectorizing.value = true
  showProgressModal.value = true // Show progress modal
  try {
    const result = await vectorizeSelectedDocs()
    console.log('Batch vectorization complete:', result)
    // Keep modal open to show results
  } catch (error) {
    console.error('Batch vectorization failed:', error)
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
    for (const docId of failedDocs) {
      try {
        await vectorizeDocument(docId)
      } catch (error) {
        console.error(`Failed to retry vectorization for ${docId}:`, error)
      }
    }
    isVectorizing.value = false
  }
}

const handleCancelVectorization = () => {
  // Stop ongoing vectorization
  isVectorizing.value = false
  showProgressModal.value = false
  // Note: Actual cancellation of backend jobs would need additional backend support
  console.log('Vectorization cancelled by user')
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
    await loadKnowledgeTree()

    console.log(`${categoryId} population completed:`, result)
  } catch (error) {
    console.error(`Failed to populate ${categoryId}:`, error)
    populationStates.value[categoryId] = { isPopulating: false, progress: 0 }
  }
}

const loadFolderContents = async (folder: TreeNode) => {
  try {
    // Load files for this category
    const response = await apiClient.post('/api/knowledge_base/search', {
      query: '',
      category: folder.category,
      n_results: 100
    })
    const data = await parseApiResponse(response)

    if (data.results && Array.isArray(data.results)) {
      folder.children = data.results.map((item: any, idx: number) => ({
        id: `file-${folder.id}-${idx}`,
        name: item.metadata?.title || item.metadata?.source || `Document ${idx + 1}`,
        type: 'file' as const,
        path: `${folder.path}/${item.metadata?.title || item.metadata?.source}`,
        size: item.content?.length || 0,
        date: item.metadata?.timestamp,
        category: folder.category,
        metadata: item
      }))
    }
  } catch (err: any) {
    console.error('Failed to load folder contents:', err)
  }
}

const loadFileContent = async (file: TreeNode) => {
  isLoadingContent.value = true
  contentError.value = null

  try {
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
        const apiResponse = await apiClient.get(`/api/knowledge_base/fact/${factKey}`)
        const response = await parseApiResponse(apiResponse)

        if (response && response.content) {
          fileContent.value = response.content
        } else {
          fileContent.value = file.content || 'Content not available'
        }
      } else {
        fileContent.value = file.content || 'Content not available'
      }
    }
  } catch (err: any) {
    console.error('Failed to load file content:', err)
    contentError.value = err.message || 'Failed to load file content'
    // Fallback to showing whatever content we have
    fileContent.value = file.content || 'Failed to load full content'
  } finally {
    isLoadingContent.value = false
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

const clearSelection = () => {
  selectedFile.value = null
  fileContent.value = ''
  contentError.value = null
}

const handleSearch = () => {
  // Search is handled by computed property
}

const clearSearch = () => {
  searchQuery.value = ''
  expandedNodes.value.clear()
}

// Utility functions (now using composable)
const getFileIcon = (node: TreeNode): string => {
  if (node.type === 'folder') {
    return expandedNodes.value.has(node.id) ? 'fas fa-folder-open' : 'fas fa-folder'
  }

  return getFileIconUtil(node.name, false)
}

// Lifecycle
onMounted(() => {
  loadMainCategories()
  loadKnowledgeTree()

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
  loadKnowledgeTree()
  clearSelection()
  expandedNodes.value.clear()
})
</script>

<style scoped>
.knowledge-file-browser {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #f9fafb;
}

/* Main Categories */
.main-categories {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.75rem;
  padding: 0.75rem;
  background: white;
  border-bottom: 1px solid #e5e7eb;
}

.main-category-card {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem;
  border: 2px solid;
  border-radius: 8px;
  background: white;
  cursor: pointer;
  transition: all 0.2s;
}

.main-category-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 16px rgba(0, 0, 0, 0.1);
}

.category-icon {
  width: 48px;
  height: 48px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 1.5rem;
  flex-shrink: 0;
}

.category-info {
  flex: 1;
}

.category-info h3 {
  font-size: 1rem;
  font-weight: 600;
  color: #111827;
  margin: 0 0 0.25rem 0;
}

.category-info p {
  font-size: 0.8125rem;
  color: #6b7280;
  margin: 0 0 0.375rem 0;
  line-height: 1.3;
}

.category-stats {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.fact-count {
  font-size: 0.875rem;
  font-weight: 500;
  color: #374151;
  background: #f3f4f6;
  padding: 0.25rem 0.75rem;
  border-radius: 6px;
}

/* Populate button spacing */
.populate-btn {
  margin-left: 0.5rem;
}

/* Header */
.browser-header {
  background: white;
  padding: 1rem;
  border-bottom: 2px solid #e5e7eb;
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}

/* Category Tabs */
.category-tabs {
  display: flex;
  gap: 0.5rem;
  overflow-x: auto;
  flex: 0 0 auto;
}

.category-tab {
  white-space: nowrap;
}

.category-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.5rem;
  height: 1.25rem;
  padding: 0 0.375rem;
  background: rgba(255, 255, 255, 0.3);
  border-radius: 0.625rem;
  font-size: 0.75rem;
  font-weight: 600;
}

/* Batch Toolbar */
.batch-toolbar {
  position: sticky;
  top: 0;
  z-index: 100;
  background: linear-gradient(135deg, #3b82f6, #2563eb);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
  padding: 0.75rem 1.5rem;
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
  gap: 0.75rem;
  color: white;
  font-weight: 500;
}

.toolbar-info i {
  font-size: 1.25rem;
}

.toolbar-actions {
  display: flex;
  gap: 0.75rem;
}

/* Toolbar button custom styling */
.toolbar-btn.vectorize {
  background: white;
  color: #3b82f6;
}

.toolbar-btn.cancel {
  background: rgba(255, 255, 255, 0.2);
  color: white;
  border: 1px solid rgba(255, 255, 255, 0.3);
}

.slide-down-enter-active,
.slide-down-leave-active {
  transition: all 0.3s ease;
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
  color: #9ca3af;
}

.search-input {
  width: 100%;
  padding: 0.625rem 2.5rem 0.625rem 2.5rem;
  border: 1px solid #d1d5db;
  border-radius: 0.5rem;
  font-size: 0.875rem;
  transition: all 0.2s;
}

.search-input:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.clear-btn {
  position: absolute;
  right: 0.5rem;
}

/* Breadcrumb */
.breadcrumb {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1.5rem;
  background: white;
  border-bottom: 1px solid #e5e7eb;
  font-size: 0.875rem;
}

.breadcrumb-item.active {
  color: #1f2937;
  cursor: default;
}

.breadcrumb-sep {
  color: #d1d5db;
  font-size: 0.75rem;
}

/* Split pane layout */
.split-pane {
  display: grid;
  grid-template-columns: 30% 70%;
  flex: 1;
  overflow: hidden;
  gap: 0;
}

.tree-pane {
  background: white;
  border-right: 2px solid #e5e7eb;
  overflow-y: auto;
  overflow-x: hidden;
}

.content-pane {
  background: #f9fafb;
  overflow-y: auto;
}

/* Tree container */
.tree-container {
  padding: 0.5rem;
}

/* Load More button container */
.load-more-container {
  display: flex;
  justify-content: center;
  padding: 1rem;
  margin-top: 0.5rem;
}

.loading-more {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 1rem;
  color: #6b7280;
  font-size: 0.875rem;
}

.loading-more i {
  font-size: 1rem;
}

/* States */
.loading-state,
.error-state,
.placeholder-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 1.5rem;
  text-align: center;
  color: #6b7280;
}

.loading-state i,
.error-state i,
.placeholder-state i {
  font-size: 3rem;
  margin-bottom: 1rem;
  opacity: 0.5;
}

.error-state {
  color: #dc2626;
}

.retry-btn {
  margin-top: 1rem;
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
  padding: 1.5rem;
  background: white;
  border-bottom: 2px solid #e5e7eb;
}

.file-info {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  flex: 1;
}

.file-info > i {
  font-size: 2rem;
  color: #3b82f6;
  margin-top: 0.25rem;
}

.file-info h4 {
  font-size: 1.125rem;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 0.25rem;
}

.file-meta {
  font-size: 0.75rem;
  color: #6b7280;
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
  background: white;
  margin: 1rem;
  border-radius: 0.5rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.loading-content,
.error-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem;
  color: #6b7280;
}

.error-content {
  color: #dc2626;
}

.content-display {
  padding: 1.5rem;
  font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
  font-size: 0.875rem;
  line-height: 1.6;
  color: #1f2937;
  white-space: pre-wrap;
  word-wrap: break-word;
  margin: 0;
}

/* Scrollbar styling */
.tree-pane::-webkit-scrollbar,
.content-pane::-webkit-scrollbar {
  width: 8px;
}

.tree-pane::-webkit-scrollbar-track,
.content-pane::-webkit-scrollbar-track {
  background: #f1f1f1;
}

.tree-pane::-webkit-scrollbar-thumb,
.content-pane::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 4px;
}

.tree-pane::-webkit-scrollbar-thumb:hover,
.content-pane::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}
</style>
