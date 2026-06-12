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
            <h3><Icon name="files" /> {{ $t('fileBrowser.browser.contentsOf', { path: selectedPath || '/' }) }}</h3>

            <!-- File Upload (Inline) -->
            <FileUpload
              ref="fileUploadRef"
              @files-selected="handleFileSelected"
              class="file-upload-inline"
            />

            <div class="file-actions-inline">
              <button @click="refreshFiles" :aria-label="t('fileBrowser.browser.refreshAriaLabel')">
                <Icon name="sync-alt" /> {{ $t('fileBrowser.browser.refresh') }}
              </button>
              <button @click="toggleView" :aria-label="t('fileBrowser.browser.toggleViewAriaLabel')">
                <i :class="viewMode === 'tree' ? 'list' : 'tree'"></i>
                {{ viewMode === 'tree' ? $t('fileBrowser.browser.listView') : $t('fileBrowser.browser.treeView') }}
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
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useUserStore } from '@/stores/useUserStore'
import { useFileBrowser } from '@/composables/file-browser/useFileBrowser'
import { useAsyncHandler } from '@/composables/useErrorHandler'
import { useSessionActivityLogger } from '@/composables/useSessionActivityLogger'

const { t } = useI18n()

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

// Composable for all file browser API calls
const {
  files,
  directoryTree,
  previewFile,
  fetchFiles,
  fetchTree,
  uploadFiles: composableUploadFiles,
  fetchPreview,
  deleteFileOrFolder,
  renameFileOrFolder,
  createDirectory
} = useFileBrowser()

// UI state (not managed by composable)
const currentPath = ref('/')
const selectedPath = ref('')
const viewMode = ref<'tree' | 'list'>('tree')
const sortField = ref('name')
const sortOrder = ref<'asc' | 'desc'>('asc')
const showPreview = ref(false)

const userStore = useUserStore()

// Computed properties
const sortedFiles = computed(() => {
  const sorted = [...files.value].sort((a, b) => {
    let aVal: string | number | Date = a.name
    let bVal: string | number | Date = b.name

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
    await fetchFiles(currentPath.value)

    if (viewMode.value === 'tree') {
      await loadDirectoryTree()
    }
  },
  {
    logErrors: true,
    errorPrefix: '[FileBrowser]'
  }
)

const { execute: loadDirectoryTree, loading: isLoadingTree } = useAsyncHandler(
  async () => {
    await fetchTree()
  },
  {
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
    await composableUploadFiles(fileList, currentPath.value)
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
      alert(t('fileBrowser.browser.uploadFailed', { error: 'Please check file size limits and format requirements' }))
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
    await fetchPreview(file, getFileType)
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
    await deleteFileOrFolder(file.path)
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
      alert(t('fileBrowser.browser.errorDeletingFile'))
    },
    logErrors: true,
    errorPrefix: '[FileBrowser]'
  }
)

const deleteFile = async (file: any) => {
  const message = t('fileBrowser.browser.deleteConfirm', { name: file.name })

  if (confirm(message)) {
    await performDelete(file)
  }
}

const { execute: performRename, loading: isRenamingFile } = useAsyncHandler(
  async (file: any, newName: string) => {
    await renameFileOrFolder(file.path, newName)
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
      alert(t('fileBrowser.browser.errorRenamingFile'))
    },
    logErrors: true,
    errorPrefix: '[FileBrowser]'
  }
)

const renameFile = async (file: any) => {
  const newName = prompt(t('fileBrowser.browser.renamePrompt'), file.name)

  if (newName && newName !== file.name) {
    await performRename(file, newName)
  }
}

const { execute: performCreateFolder, loading: isCreatingFolder } = useAsyncHandler(
  async (folderName: string) => {
    await createDirectory(currentPath.value, folderName)
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
      alert(t('fileBrowser.browser.errorCreatingFolder'))
    },
    logErrors: true,
    errorPrefix: '[FileBrowser]'
  }
)

const createNewFolder = async () => {
  const folderName = prompt(t('fileBrowser.browser.createFolderPrompt'))

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
@reference "../../assets/tailwind.css";
.file-browser {
  @apply h-full flex flex-col bg-autobot-bg-tertiary p-6;
}

.file-content-container {
  @apply flex-1 flex flex-col min-h-0;
}

.tree-view {
  @apply flex gap-6 h-full;
}

.files-panel {
  @apply flex-1 bg-autobot-bg-card border border-autobot-border rounded-lg;
}

.files-header {
  @apply p-4 border-b border-autobot-border bg-autobot-bg-tertiary flex flex-wrap items-center gap-4;
}

.files-header h3 {
  @apply text-lg font-semibold text-autobot-text-primary flex items-center gap-2 flex-shrink-0;
}

.file-upload-inline {
  @apply flex-1 min-w-0;
}

/* Style FileUpload component when used inline */
.file-upload-inline :deep(.file-upload-section) {
  @apply mb-0 p-0 border border-autobot-border rounded-md bg-autobot-bg-card hover:border-autobot-border;
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
  @apply flex gap-2 shrink-0 ml-auto;
}

.file-actions-inline button {
  @apply px-4 py-2 text-sm font-medium text-autobot-text-secondary bg-autobot-bg-card border border-autobot-border rounded-md hover:bg-autobot-bg-secondary focus:outline-none focus:ring-2 focus:ring-blue-500 flex items-center gap-2;
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
  z-index: var(--z-toast);
}

.modal-content {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  max-width: 90vw;
  max-height: 90vh;
  width: 800px;
  height: 600px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: var(--shadow-lg);
}

.modal-header {
  padding: var(--spacing-4) var(--spacing-6);
  border-bottom: 1px solid var(--border-default);
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: var(--bg-secondary);
}

.modal-header h3 {
  margin: var(--spacing-0);
  font-size: var(--text-lg);
  color: var(--text-primary);
  word-break: break-all;
}

.close-btn {
  background: none;
  border: none;
  font-size: var(--text-2xl);
  color: var(--text-muted);
  cursor: pointer;
  padding: var(--spacing-0);
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-default);
  transition: background-color var(--duration-200);
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
  padding: var(--spacing-5);
  background-color: var(--bg-secondary);
}

.preview-image {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: var(--radius-default);
  box-shadow: var(--shadow-sm);
}

/* Text/Code Preview */
.text-preview, .json-preview {
  flex: 1;
  overflow: auto;
  padding: var(--spacing-5);
}

.text-preview pre, .json-preview pre {
  margin: var(--spacing-0);
  font-family: 'Courier New', Courier, monospace;
  font-size: var(--text-sm);
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  background-color: var(--bg-secondary);
  color: var(--text-primary);
  padding: var(--spacing-4);
  border-radius: var(--radius-default);
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
  padding: var(--spacing-10);
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
  background-color: var(--bg-secondary);
}

.file-info p {
  margin: var(--spacing-2) var(--spacing-0);
  font-size: var(--text-base);
  color: var(--text-primary);
}

.file-info p strong {
  color: var(--color-electric-500, #3b82f6);
}

.download-btn {
  margin-top: var(--spacing-5);
  padding: var(--spacing-2-5) var(--spacing-5);
  background-color: var(--color-electric-600, #2563eb);
  color: white;
  border: none;
  border-radius: var(--radius-default);
  cursor: pointer;
  font-size: var(--text-base);
  transition: background-color var(--duration-200);
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
    padding: var(--spacing-3) var(--spacing-4);
  }

  .modal-header h3 {
    font-size: var(--text-base);
  }

  .text-preview, .json-preview {
    padding: var(--spacing-4);
  }

  .text-preview pre, .json-preview pre {
    font-size: var(--text-xs);
    padding: var(--spacing-3);
  }
}
</style>
