<template>
  <div class="knowledge-file-browser">
    <!-- Header -->
    <div class="browser-header">
      <div class="header-content">
        <h3>
          <i :class="mode === 'user' ? 'fas fa-user' : 'fas fa-robot'"></i>
          {{ mode === 'user' ? 'User Knowledge' : 'AutoBot Knowledge' }} Browser
        </h3>
        <p class="subtitle">Browse files and folders in a classic tree view</p>
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
        <button v-if="searchQuery" @click="clearSearch" class="clear-btn">
          <i class="fas fa-times"></i>
        </button>
      </div>
    </div>

    <!-- Breadcrumb navigation -->
    <div v-if="selectedFile" class="breadcrumb">
      <button @click="clearSelection" class="breadcrumb-item">
        <i class="fas fa-home"></i> Root
      </button>
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
          <button @click="loadKnowledgeTree" class="retry-btn">
            <i class="fas fa-redo"></i> Retry
          </button>
        </div>

        <div v-else class="tree-container">
          <div v-if="filteredTree.length === 0" class="empty-state">
            <i class="fas fa-folder-open"></i>
            <p>No items found</p>
          </div>
          <TreeNodeComponent
            v-for="node in filteredTree"
            :key="node.id"
            :node="node"
            :expanded-nodes="expandedNodes"
            :selected-id="selectedFile?.id"
            @toggle="toggleNode"
            @select="selectNode"
          />
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
            <button @click="clearSelection" class="close-btn">
              <i class="fas fa-times"></i>
            </button>
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
import { ref, computed, onMounted, watch, defineComponent, h } from 'vue'
import apiClient from '@/utils/ApiClient'
import { useKnowledgeBase } from '@/composables/useKnowledgeBase'

// Use the shared composable
const {
  formatCategoryName,
  getFileIcon: getFileIconUtil,
  formatFileSize,
  formatDateOnly: formatDate
} = useKnowledgeBase()

// Props
interface Props {
  mode: 'user' | 'autobot'
}

const props = withDefaults(defineProps<Props>(), {
  mode: 'user'
})

// Tree node interface
interface TreeNode {
  id: string
  name: string
  type: 'folder' | 'file'
  path: string
  children?: TreeNode[]
  size?: number
  date?: string
  category?: string
  metadata?: any
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

// Computed
const breadcrumbParts = computed(() => {
  if (!selectedFile.value) return []
  return selectedFile.value.path.split('/').filter(p => p)
})

const filteredTree = computed(() => {
  if (!searchQuery.value) return treeData.value

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

  return filterNodes(treeData.value)
})

// Methods
const loadKnowledgeTree = async () => {
  isLoading.value = true
  error.value = null

  try {
    const response = await apiClient.get('/api/knowledge_base/stats/basic')
    const data = await response.json()

    // Build tree structure from API data
    if (props.mode === 'autobot') {
      // System knowledge (categories from stats)
      const categories = data.categories || []
      treeData.value = categories.map((category: string, idx: number) => ({
        id: `folder-${idx}`,
        name: formatCategoryName(category),
        type: 'folder' as const,
        path: `/${category}`,
        category: category,
        children: [] // Will be loaded on expand
      }))
    } else {
      // User knowledge - fetch from entries
      await loadUserKnowledge()
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
    const response = await apiClient.get('/api/knowledge_base/entries')
    const data = await response.json()

    // Build tree from entries (group by category)
    const categoryMap = new Map<string, TreeNode[]>()

    if (data.entries && Array.isArray(data.entries)) {
      data.entries.forEach((entry: any, idx: number) => {
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

    // Convert to tree structure
    treeData.value = Array.from(categoryMap.entries()).map(([category, files], idx) => ({
      id: `folder-${idx}`,
      name: formatCategoryName(category),
      type: 'folder' as const,
      path: `/${category}`,
      category: category,
      children: files
    }))
  } catch (err: any) {
    console.error('Failed to load user knowledge:', err)
    error.value = err.message || 'Failed to load user knowledge'
  }
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

const loadFolderContents = async (folder: TreeNode) => {
  try {
    // Load files for this category
    const response = await apiClient.post('/api/knowledge_base/search', {
      query: '',
      category: folder.category,
      n_results: 100
    })
    const data = await response.json()

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
    // Extract content from metadata if available
    if (file.metadata?.content) {
      fileContent.value = file.metadata.content
    } else if (file.metadata?.document) {
      fileContent.value = file.metadata.document
    } else {
      // Try to search for the specific file
      const response = await apiClient.post('/api/knowledge_base/search', {
        query: file.name,
        category: file.category,
        n_results: 1
      })
      const data = await response.json()

      if (data.results && data.results.length > 0) {
        fileContent.value = data.results[0].content || data.results[0].document || 'No content available'
      } else {
        fileContent.value = 'Content not found'
      }
    }
  } catch (err: any) {
    console.error('Failed to load file content:', err)
    contentError.value = err.message || 'Failed to load file content'
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
// Removed: formatCategoryName - now using composable
// Removed: formatFileSize - now using composable
// Removed: formatDate - now using composable

const getFileIcon = (node: TreeNode): string => {
  if (node.type === 'folder') {
    return expandedNodes.value.has(node.id) ? 'fas fa-folder-open' : 'fas fa-folder'
  }

  return getFileIconUtil(node.name, false)
}

// TreeNode recursive component (defined inline)
const TreeNodeComponent: any = defineComponent({
  name: 'TreeNodeComponent',
  props: {
    node: {
      type: Object as () => TreeNode,
      required: true
    },
    expandedNodes: {
      type: Set as () => Set<string>,
      required: true
    },
    selectedId: {
      type: String,
      default: undefined
    }
  },
  emits: ['toggle', 'select'],
  setup(props, { emit }) {
    const getNodeIcon = () => {
      if (props.node.type === 'folder') {
        return props.expandedNodes.has(props.node.id) ? 'fas fa-folder-open' : 'fas fa-folder'
      }
      return 'fas fa-file-alt'
    }

    const formatSize = (bytes: number) => {
      if (bytes < 1024) return `${bytes}B`
      if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}KB`
      return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
    }

    return () => h('div', { class: 'tree-node' }, [
      h('div', {
        class: {
          'node-content': true,
          'is-folder': props.node.type === 'folder',
          'is-file': props.node.type === 'file',
          'is-expanded': props.node.type === 'folder' && props.expandedNodes.has(props.node.id),
          'is-selected': props.node.id === props.selectedId
        },
        onClick: () => emit('select', props.node)
      }, [
        props.node.type === 'folder'
          ? h('button', {
              class: 'expand-btn',
              onClick: (e: Event) => {
                e.stopPropagation()
                emit('toggle', props.node.id)
              }
            }, [
              h('i', {
                class: ['fas', props.expandedNodes.has(props.node.id) ? 'fa-chevron-down' : 'fa-chevron-right']
              })
            ])
          : h('span', { class: 'expand-spacer' }),
        h('i', { class: ['node-icon', getNodeIcon()] }),
        h('span', { class: 'node-name' }, props.node.name),
        props.node.type === 'file' && props.node.size
          ? h('span', { class: 'node-size' }, formatSize(props.node.size))
          : null
      ]),
      props.node.type === 'folder' && props.expandedNodes.has(props.node.id) && props.node.children
        ? h('div', { class: 'node-children' },
            props.node.children.map(child =>
              h(TreeNodeComponent, {
                key: child.id,
                node: child,
                expandedNodes: props.expandedNodes,
                selectedId: props.selectedId,
                onToggle: (id: string) => emit('toggle', id),
                onSelect: (node: TreeNode) => emit('select', node)
              })
            )
          )
        : null
    ])
  }
})

// Lifecycle
onMounted(() => {
  loadKnowledgeTree()
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

/* Header */
.browser-header {
  background: white;
  padding: 1.5rem;
  border-bottom: 2px solid #e5e7eb;
}

.header-content {
  margin-bottom: 1rem;
}

.header-content h3 {
  font-size: 1.5rem;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 0.25rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.subtitle {
  color: #6b7280;
  font-size: 0.875rem;
}

.search-bar {
  position: relative;
  display: flex;
  align-items: center;
  max-width: 500px;
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
  padding: 0.25rem 0.5rem;
  background: none;
  border: none;
  color: #9ca3af;
  cursor: pointer;
  transition: color 0.2s;
}

.clear-btn:hover {
  color: #6b7280;
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

.breadcrumb-item {
  color: #3b82f6;
  background: none;
  border: none;
  cursor: pointer;
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
  transition: background 0.2s;
}

.breadcrumb-item:hover {
  background: #eff6ff;
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

/* Tree node */
.tree-node {
  user-select: none;
}

.node-content {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  cursor: pointer;
  border-radius: 0.375rem;
  transition: all 0.15s;
  margin: 0.125rem 0;
}

.node-content:hover {
  background: #f3f4f6;
}

.node-content.is-selected {
  background: #eff6ff;
  color: #3b82f6;
  font-weight: 500;
}

.expand-btn {
  width: 1.25rem;
  height: 1.25rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  color: #6b7280;
  cursor: pointer;
  padding: 0;
  transition: transform 0.2s;
}

.expand-btn:hover {
  color: #374151;
}

.expand-spacer {
  width: 1.25rem;
}

.node-icon {
  color: #3b82f6;
  font-size: 0.875rem;
  min-width: 1rem;
}

.node-name {
  flex: 1;
  font-size: 0.875rem;
  color: #374151;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-size {
  font-size: 0.75rem;
  color: #9ca3af;
}

.node-children {
  padding-left: 1.5rem;
}

/* States */
.loading-state,
.error-state,
.empty-state,
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
.empty-state i,
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
  padding: 0.5rem 1rem;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 0.375rem;
  cursor: pointer;
  font-weight: 500;
  transition: background 0.2s;
}

.retry-btn:hover {
  background: #2563eb;
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
  background: #f3f4f6;
  border: none;
  border-radius: 0.375rem;
  color: #6b7280;
  cursor: pointer;
  transition: all 0.2s;
}

.close-btn:hover {
  background: #e5e7eb;
  color: #374151;
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
