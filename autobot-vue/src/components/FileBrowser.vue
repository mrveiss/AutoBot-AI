<template>
  <div class="file-browser">
    <!-- Header -->
    <FileBrowserHeader
      :view-mode="viewMode"
      @refresh="refreshFiles"
      @upload="triggerFileUpload"
      @toggle-view="toggleView"
    />

    <!-- Path Navigation -->
    <FilePathNavigation
      :current-path="currentPath"
      @navigate-to-path="navigateToPath"
    />

    <!-- File Upload -->
    <FileUpload
      ref="fileUploadRef"
      @files-selected="handleFileSelected"
    />

    <!-- File Preview Modal -->
    <FilePreview
      :show-preview="showPreview"
      :preview-file="previewFile"
      @close="closePreview"
      @download="downloadPreviewFile"
    />

    <!-- Main Content Area -->
    <div class="file-content-container">
      <!-- Tree View -->
      <div v-if="viewMode === 'tree'" class="tree-view">
        <FileTreeView
          :directory-tree="directoryTree"
          :selected-path="selectedPath"
          @toggle-node="toggleNode"
          @expand-all="expandAll"
          @collapse-all="collapseAll"
        />

        <!-- File List Panel in Tree View -->
        <div class="files-panel">
          <div class="files-header">
            <h3><i class="fas fa-files"></i> {{ selectedPath || '/' }} Contents</h3>
          </div>
          <FileListTable
            :files="sortedFiles"
            :sort-field="sortField"
            :sort-order="sortOrder"
            :current-path="currentPath"
            @sort="sortBy"
            @navigate="navigateToPath"
            @view-file="viewFile"
            @delete-file="deleteFile"
          />
        </div>
      </div>

      <!-- List View -->
      <div v-else class="list-view">
        <FileListTable
          :files="sortedFiles"
          :sort-field="sortField"
          :sort-order="sortOrder"
          :current-path="currentPath"
          @sort="sortBy"
          @navigate="navigateToPath"
          @view-file="viewFile"
          @delete-file="deleteFile"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import apiClient from '@/utils/ApiClient.js'
import { useUserStore } from '@/stores/useUserStore'

// Import components
import FileBrowserHeader from './file-browser/FileBrowserHeader.vue'
import FilePathNavigation from './file-browser/FilePathNavigation.vue'
import FileUpload from './file-browser/FileUpload.vue'
import FilePreview from './file-browser/FilePreview.vue'
import FileTreeView from './file-browser/FileTreeView.vue'
import FileListTable from './file-browser/FileListTable.vue'

// Component props
interface Props {
  chatContext?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  chatContext: false
})

// Template refs
const fileUploadRef = ref<InstanceType<typeof FileUpload>>()

// State
const files = ref<any[]>([])
const directoryTree = ref<any[]>([])
const currentPath = ref('/')
const selectedPath = ref('')
const viewMode = ref<'tree' | 'list'>('tree')
const sortField = ref('name')
const sortOrder = ref<'asc' | 'desc'>('asc')
const showPreview = ref(false)
const previewFile = ref<any>(null)

const userStore = useUserStore()

// Computed properties
const sortedFiles = computed(() => {
  const sorted = [...files.value].sort((a, b) => {
    let aVal = a[sortField.value]
    let bVal = b[sortField.value]

    // Handle different sort fields
    if (sortField.value === 'size') {
      aVal = a.size || 0
      bVal = b.size || 0
    } else if (sortField.value === 'modified') {
      aVal = new Date(a.last_modified || 0)
      bVal = new Date(b.last_modified || 0)
    } else if (sortField.value === 'type') {
      aVal = a.is_dir ? 'Directory' : getFileType(a.name)
      bVal = b.is_dir ? 'Directory' : getFileType(b.name)
    }

    // Sort directories first
    if (a.is_dir && !b.is_dir) return -1
    if (!a.is_dir && b.is_dir) return 1

    // Then sort by field
    if (aVal < bVal) return sortOrder.value === 'asc' ? -1 : 1
    if (aVal > bVal) return sortOrder.value === 'asc' ? 1 : -1
    return 0
  })

  return sorted
})

// Methods
const refreshFiles = async () => {
  try {
    const response = await apiClient.get(`/api/files/list?path=${encodeURIComponent(currentPath.value)}`)
    const data = await response.json()
    files.value = data.files || []

    if (viewMode.value === 'tree') {
      await loadDirectoryTree()
    }
  } catch (error) {
    console.error('Failed to load files:', error)
    files.value = []
  }
}

const loadDirectoryTree = async () => {
  try {
    const response = await apiClient.get('/api/files/tree')
    const data = await response.json()
    directoryTree.value = data.tree || []
  } catch (error) {
    console.error('Failed to load directory tree:', error)
    directoryTree.value = []
  }
}

const navigateToPath = (path: string) => {
  currentPath.value = path
  selectedPath.value = path
  refreshFiles()
}

const toggleView = () => {
  viewMode.value = viewMode.value === 'tree' ? 'list' : 'tree'
  if (viewMode.value === 'tree') {
    loadDirectoryTree()
  }
}

const sortBy = (field: string) => {
  if (sortField.value === field) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortField.value = field
    sortOrder.value = 'asc'
  }
}

const triggerFileUpload = () => {
  fileUploadRef.value?.triggerFileSelect()
}

const handleFileSelected = async (fileList: FileList) => {
  const formData = new FormData()

  Array.from(fileList).forEach((file) => {
    formData.append('files', file)
  })

  formData.append('path', currentPath.value)

  try {
    await apiClient.post('/api/files/upload', formData)
    await refreshFiles()
  } catch (error) {
    console.error('Failed to upload files:', error)
  }
}

const viewFile = async (file: any) => {
  try {
    const response = await apiClient.get(`/api/files/preview?path=${encodeURIComponent(file.path)}`)
    const data = await response.json()
    previewFile.value = {
      name: file.name,
      type: data.type,
      url: data.url,
      content: data.content,
      fileType: getFileType(file.name),
      size: file.size
    }
    showPreview.value = true
  } catch (error) {
    console.error('Failed to preview file:', error)
  }
}

const deleteFile = async (file: any) => {
  if (confirm(`Are you sure you want to delete "${file.name}"?`)) {
    try {
      await apiClient.delete(`/api/files/delete?path=${encodeURIComponent(file.path)}`)
      await refreshFiles()
    } catch (error) {
      console.error('Failed to delete file:', error)
    }
  }
}

const closePreview = () => {
  showPreview.value = false
  previewFile.value = null
}

const downloadPreviewFile = (file: any) => {
  if (file.url) {
    const a = document.createElement('a')
    a.href = file.url
    a.download = file.name
    a.click()
  }
}

const toggleNode = (item: any) => {
  if (item.is_dir) {
    item.expanded = !item.expanded
    selectedPath.value = item.path
    navigateToPath(item.path)
  }
}

const expandAll = () => {
  const expandNodeRecursively = (nodes: any[]) => {
    nodes.forEach(node => {
      if (node.is_dir) {
        node.expanded = true
        if (node.children) {
          expandNodeRecursively(node.children)
        }
      }
    })
  }
  expandNodeRecursively(directoryTree.value)
}

const collapseAll = () => {
  const collapseNodeRecursively = (nodes: any[]) => {
    nodes.forEach(node => {
      if (node.is_dir) {
        node.expanded = false
        if (node.children) {
          collapseNodeRecursively(node.children)
        }
      }
    })
  }
  collapseNodeRecursively(directoryTree.value)
}

// Helper methods
const getFileType = (filename: string): string => {
  const extension = filename.split('.').pop()?.toLowerCase()
  if (!extension) return 'Unknown'

  const typeMap: Record<string, string> = {
    txt: 'Text',
    md: 'Markdown',
    js: 'JavaScript',
    ts: 'TypeScript',
    html: 'HTML',
    css: 'CSS',
    vue: 'Vue Component',
    json: 'JSON',
    jpg: 'JPEG Image',
    jpeg: 'JPEG Image',
    png: 'PNG Image',
    gif: 'GIF Image',
    svg: 'SVG Image',
    pdf: 'PDF Document',
    zip: 'ZIP Archive',
    tar: 'TAR Archive',
    gz: 'GZ Archive'
  }

  return typeMap[extension] || extension.toUpperCase() + ' File'
}

// Lifecycle
onMounted(() => {
  refreshFiles()
})
</script>

<style scoped>
.file-browser {
  @apply h-full flex flex-col bg-gray-50 p-6;
}

.file-content-container {
  @apply flex-1 flex flex-col min-h-0;
}

.tree-view {
  @apply flex gap-6 h-full;
}

.files-panel {
  @apply flex-1 bg-white border border-gray-200 rounded-lg;
}

.files-header {
  @apply p-4 border-b border-gray-200 bg-gray-50;
}

.files-header h3 {
  @apply text-lg font-semibold text-gray-900 flex items-center gap-2;
}

.list-view {
  @apply flex-1;
}
</style>