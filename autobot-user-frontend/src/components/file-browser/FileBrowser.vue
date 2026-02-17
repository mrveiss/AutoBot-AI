<template>
  <div class="file-browser">
    <!-- Header (with integrated path navigation) -->
    <FileBrowserHeader
      :view-mode="viewMode"
      :current-path="currentPath"
      @upload="triggerFileUpload"
      @new-folder="createNewFolder"
      @navigate-to-path="navigateToPath"
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

            <!-- File Upload (Inline) -->
            <FileUpload
              ref="fileUploadRef"
              @files-selected="handleFileSelected"
              class="file-upload-inline"
            />

            <div class="file-actions-inline">
              <button @click="refreshFiles" aria-label="Refresh files">
                <i class="fas fa-sync-alt"></i> Refresh
              </button>
              <button @click="toggleView" aria-label="Toggle view mode">
                <i :class="viewMode === 'tree' ? 'fas fa-list' : 'fas fa-tree'"></i>
                {{ viewMode === 'tree' ? 'List View' : 'Tree View' }}
              </button>
            </div>
          </div>
          <FileListTable
            :files="sortedFiles"
            :sort-field="sortField"
            :sort-order="sortOrder"
            :current-path="currentPath"
            @sort="sortBy"
            @navigate="navigateToPath"
            @view-file="viewFile"
            @rename-file="renameFile"
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
          @rename-file="renameFile"
          @delete-file="deleteFile"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import apiClient from '@/utils/ApiClient'
import { useUserStore } from '@/stores/useUserStore'
import { useAsyncHandler } from '@/composables/useErrorHandler'
import { useSessionActivityLogger } from '@/composables/useSessionActivityLogger'

// Issue #608: Activity logger for session tracking
const { logFileActivity } = useSessionActivityLogger()

// Import components
import FileBrowserHeader from './FileBrowserHeader.vue'
import FileUpload from './FileUpload.vue'
import FilePreview from './FilePreview.vue'
import FileTreeView from './FileTreeView.vue'
import FileListTable from './FileListTable.vue'

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
const { execute: refreshFiles, loading: isRefreshingFiles } = useAsyncHandler(
  async () => {
    // ApiClient.get() returns parsed JSON directly, not a Response object
    // Use type assertion since ApiClient is JavaScript
    const data = await apiClient.get(`/api/files/list?path=${encodeURIComponent(currentPath.value)}`) as any
    files.value = (data as any).files || []

    if (viewMode.value === 'tree') {
      await loadDirectoryTree()
    }
  },
  {
    onError: () => {
      files.value = []
    },
    logErrors: true,
    errorPrefix: '[FileBrowser]'
  }
)

const { execute: loadDirectoryTree, loading: isLoadingTree } = useAsyncHandler(
  async () => {
    // ApiClient.get() returns parsed JSON directly, not a Response object
    // Use type assertion since ApiClient is JavaScript
    const data = await apiClient.get('/api/files/tree') as any
    directoryTree.value = (data as any).tree || []
  },
  {
    onError: () => {
      directoryTree.value = []
    },
    logErrors: true,
    errorPrefix: '[FileBrowser]'
  }
)

const navigateToPath = (path: string) => {
  const previousPath = currentPath.value
  currentPath.value = path
  selectedPath.value = path
  refreshFiles()

  // Issue #608: Log navigation activity
  if (props.chatContext) {
    logFileActivity('navigate', path, {
      fromPath: previousPath,
      toPath: path
    })
  }
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

const { execute: uploadFiles, loading: isUploadingFiles } = useAsyncHandler(
  async (fileList: FileList) => {
    const formData = new FormData()

    Array.from(fileList).forEach((file) => {
      formData.append('files', file)
    })

    formData.append('path', currentPath.value)

    await apiClient.post('/api/files/upload', formData)
    await refreshFiles()

    // Issue #608: Log file upload activity
    if (props.chatContext) {
      const fileNames = Array.from(fileList).map(f => f.name).join(', ')
      const totalSize = Array.from(fileList).reduce((sum, f) => sum + f.size, 0)
      logFileActivity('upload', currentPath.value, {
        fileNames,
        fileCount: fileList.length,
        totalSize
      })
    }
  },
  {
    onError: () => {
      alert('Failed to upload files. Please check file size limits and format requirements, then try again.')
    },
    logErrors: true,
    errorPrefix: '[FileBrowser]'
  }
)

const handleFileSelected = async (fileList: FileList) => {
  await uploadFiles(fileList)
}

const { execute: viewFile, loading: isViewingFile } = useAsyncHandler(
  async (file: any) => {
    // ApiClient.get() returns parsed JSON directly, not a Response object
    // Use type assertion since ApiClient is JavaScript
    const data = await apiClient.get(`/api/files/preview?path=${encodeURIComponent(file.path)}`) as any
    previewFile.value = {
      name: file.name,
      type: (data as any).type,
      url: (data as any).url,
      content: (data as any).content,
      fileType: getFileType(file.name),
      size: file.size
    }
    showPreview.value = true

    // Issue #608: Log file view activity
    if (props.chatContext) {
      logFileActivity('view', file.path, {
        fileName: file.name,
        fileType: getFileType(file.name),
        size: file.size
      })
    }
  },
  {
    logErrors: true,
    errorPrefix: '[FileBrowser]'
  }
)

const { execute: performDelete, loading: isDeletingFile } = useAsyncHandler(
  async (file: any) => {
    const itemType = file.is_dir ? 'folder' : 'file'
    await apiClient.delete(`/api/files/delete?path=${encodeURIComponent(file.path)}`)
    await refreshFiles()

    // Issue #608: Log file/folder delete activity
    if (props.chatContext) {
      logFileActivity('delete', file.path, {
        fileName: file.name,
        isDir: file.is_dir,
        itemType
      })
    }
    return itemType
  },
  {
    onError: () => {
      alert(`Failed to delete item. Please try again.`)
    },
    logErrors: true,
    errorPrefix: '[FileBrowser]'
  }
)

const deleteFile = async (file: any) => {
  const message = file.is_dir
    ? `Are you sure you want to delete the folder "${file.name}" and all its contents?`
    : `Are you sure you want to delete "${file.name}"?`

  if (confirm(message)) {
    await performDelete(file)
  }
}

const { execute: performRename, loading: isRenamingFile } = useAsyncHandler(
  async (file: any, newName: string) => {
    const formData = new FormData()
    formData.append('path', file.path)
    formData.append('new_name', newName)

    await apiClient.post('/api/files/rename', formData)
    await refreshFiles()

    // Issue #608: Log file/folder rename activity
    if (props.chatContext) {
      logFileActivity('rename', file.path, {
        oldName: file.name,
        newName,
        isDir: file.is_dir
      })
    }
  },
  {
    onError: () => {
      alert(`Failed to rename item. Please try again.`)
    },
    logErrors: true,
    errorPrefix: '[FileBrowser]'
  }
)

const renameFile = async (file: any) => {
  const itemType = file.is_dir ? 'folder' : 'file'
  const newName = prompt(`Enter new name for ${itemType} "${file.name}":`, file.name)

  if (newName && newName !== file.name) {
    await performRename(file, newName)
  }
}

const { execute: performCreateFolder, loading: isCreatingFolder } = useAsyncHandler(
  async (folderName: string) => {
    const formData = new FormData()
    formData.append('path', currentPath.value)
    formData.append('name', folderName)

    await apiClient.post('/api/files/create_directory', formData)
    await refreshFiles()

    // Issue #608: Log folder creation activity
    if (props.chatContext) {
      logFileActivity('create_folder', `${currentPath.value}/${folderName}`, {
        folderName,
        parentPath: currentPath.value
      })
    }
  },
  {
    onError: () => {
      alert('Failed to create folder. Please try again.')
    },
    logErrors: true,
    errorPrefix: '[FileBrowser]'
  }
)

const createNewFolder = async () => {
  const folderName = prompt('Enter new folder name:')

  if (folderName) {
    await performCreateFolder(folderName)
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
  @apply p-4 border-b border-gray-200 bg-gray-50 flex flex-wrap items-center gap-4;
}

.files-header h3 {
  @apply text-lg font-semibold text-gray-900 flex items-center gap-2 flex-shrink-0;
}

.file-upload-inline {
  @apply flex-1 min-w-0;
}

/* Style FileUpload component when used inline */
.file-upload-inline :deep(.file-upload-section) {
  @apply mb-0 p-0 border border-gray-300 rounded-md bg-white hover:border-gray-400;
}

.file-upload-inline :deep(.file-upload-inline-wrapper) {
  @apply gap-1;
}

.file-upload-inline :deep(.file-input-label) {
  @apply text-sm gap-1;
}

.file-upload-inline :deep(.visible-file-input) {
  @apply text-sm min-w-[150px] py-0;
}

.file-actions-inline {
  @apply flex gap-2 flex-shrink-0 ml-auto;
}

.file-actions-inline button {
  @apply px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 flex items-center gap-2;
}

.file-actions-inline button:hover {
  @apply shadow-sm;
}

.file-actions-inline button i {
  @apply text-sm;
}

.list-view {
  @apply flex-1;
}

/* File Preview Modal Styles */
.file-preview-modal {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.8);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 9999;
}

.modal-content {
  background: var(--bg-card);
  border-radius: 8px;
  max-width: 90vw;
  max-height: 90vh;
  width: 800px;
  height: 600px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
}

.modal-header {
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-default);
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: var(--bg-secondary);
}

.modal-header h3 {
  margin: 0;
  font-size: 18px;
  color: var(--text-primary);
  word-break: break-all;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  color: var(--text-muted);
  cursor: pointer;
  padding: 0;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.close-btn:hover {
  background-color: var(--bg-tertiary);
  color: var(--text-primary);
}

.modal-body {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* HTML Preview */
.html-preview {
  flex: 1;
  display: flex;
}

.html-frame {
  width: 100%;
  height: 100%;
  border: none;
}

/* Image Preview */
.image-preview {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 20px;
  background-color: var(--bg-secondary);
}

.preview-image {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

/* Text/Code Preview */
.text-preview, .json-preview {
  flex: 1;
  overflow: auto;
  padding: 20px;
}

.text-preview pre, .json-preview pre {
  margin: 0;
  font-family: 'Courier New', Courier, monospace;
  font-size: 14px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  background-color: var(--bg-secondary);
  color: var(--text-primary);
  padding: 16px;
  border-radius: 4px;
  border: 1px solid var(--border-default);
}

.json-preview pre {
  background-color: var(--bg-tertiary);
  border-color: var(--border-default);
}

/* PDF Preview */
.pdf-preview {
  flex: 1;
  display: flex;
}

.pdf-frame {
  width: 100%;
  height: 100%;
  border: none;
}

/* File Info */
.file-info {
  flex: 1;
  padding: 40px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
  background-color: var(--bg-secondary);
}

.file-info p {
  margin: 8px 0;
  font-size: 16px;
  color: var(--text-primary);
}

.file-info p strong {
  color: var(--color-electric-500, #3b82f6);
}

.download-btn {
  margin-top: 20px;
  padding: 10px 20px;
  background-color: var(--color-electric-600, #2563eb);
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 16px;
  transition: background-color 0.2s;
}

.download-btn:hover {
  background-color: var(--color-electric-700, #1d4ed8);
}

/* Responsive Design */
@media (max-width: 768px) {
  .modal-content {
    width: 95vw;
    height: 85vh;
  }

  .modal-header {
    padding: 12px 16px;
  }

  .modal-header h3 {
    font-size: 16px;
  }

  .text-preview, .json-preview {
    padding: 16px;
  }

  .text-preview pre, .json-preview pre {
    font-size: 12px;
    padding: 12px;
  }
}
</style>
