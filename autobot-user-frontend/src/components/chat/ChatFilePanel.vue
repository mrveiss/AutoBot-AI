<template>
  <div class="chat-file-panel h-full flex flex-col bg-autobot-bg-card border-l border-blueGray-200">
    <!-- Header -->
    <div class="flex items-center justify-between p-3 border-b border-blueGray-200 flex-shrink-0">
      <div class="flex items-center gap-2">
        <i class="fas fa-folder text-blueGray-600"></i>
        <h3 class="text-sm font-semibold text-blueGray-700">File Manager</h3>
      </div>
      <div class="flex items-center gap-1">
        <button @click="showCreateDialog = true" class="action-btn" title="New file (Ctrl+N)">
          <i class="fas fa-plus text-xs"></i>
        </button>
        <button @click="viewMode = viewMode === 'list' ? 'grid' : 'list'" class="action-btn" :title="viewMode === 'list' ? 'Grid view' : 'List view'">
          <i :class="viewMode === 'list' ? 'fas fa-th' : 'fas fa-list'" class="text-xs"></i>
        </button>
        <button @click="$emit('close')" class="action-btn" title="Close panel">
          <i class="fas fa-times text-xs"></i>
        </button>
      </div>
    </div>

    <!-- File Statistics & Search -->
    <div class="px-3 py-2 border-b border-blueGray-200 flex-shrink-0 space-y-2">
      <div v-if="stats.total_files > 0" class="flex justify-between text-xs text-blueGray-600">
        <span>{{ stats.total_files }} file{{ stats.total_files > 1 ? 's' : '' }}</span>
        <span>{{ totalSizeFormatted }}</span>
      </div>
      <!-- Search -->
      <div class="relative">
        <i class="fas fa-search absolute left-2 top-1/2 -translate-y-1/2 text-blueGray-400 text-xs"></i>
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Search files..."
          class="w-full pl-7 pr-2 py-1.5 text-xs border border-blueGray-200 rounded-md focus:outline-none focus:border-indigo-400 bg-blueGray-50"
        />
      </div>
      <!-- Sort -->
      <div class="flex items-center gap-1 text-xs">
        <span class="text-blueGray-500">Sort:</span>
        <button
          v-for="opt in sortOptions"
          :key="opt.field"
          @click="setSort(opt.field)"
          class="px-1.5 py-0.5 rounded transition-colors"
          :class="sortField === opt.field ? 'bg-indigo-100 text-indigo-700' : 'text-blueGray-500 hover:bg-blueGray-100'"
        >
          {{ opt.label }}
          <i v-if="sortField === opt.field" :class="sortDirection === 'asc' ? 'fas fa-sort-up' : 'fas fa-sort-down'" class="text-xs ml-0.5"></i>
        </button>
      </div>
      <!-- Bulk actions -->
      <div v-if="selectedCount > 0" class="flex items-center justify-between bg-indigo-50 rounded-md px-2 py-1">
        <span class="text-xs text-indigo-700">{{ selectedCount }} selected</span>
        <div class="flex gap-1">
          <button @click="handleBulkDelete" class="text-xs text-red-600 hover:text-red-800 px-1">Delete</button>
          <button @click="selectAllFiles" class="text-xs text-indigo-600 hover:text-indigo-800 px-1">
            {{ allSelected ? 'Deselect' : 'Select all' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Upload Area -->
    <div class="p-3 border-b border-blueGray-200 flex-shrink-0">
      <div
        class="upload-area border-2 border-dashed rounded-lg p-3 text-center transition-colors cursor-pointer"
        :class="[
          isDragging
            ? 'border-indigo-500 bg-indigo-50'
            : 'border-blueGray-300 bg-blueGray-50 hover:border-blueGray-400 hover:bg-blueGray-100'
        ]"
        @click="triggerFileInput"
        @dragover.prevent="isDragging = true"
        @dragleave.prevent="isDragging = false"
        @drop.prevent="handleDrop"
      >
        <i class="fas fa-cloud-upload-alt text-2xl mb-1" :class="isDragging ? 'text-indigo-600' : 'text-blueGray-400'"></i>
        <p class="text-xs text-blueGray-600">
          {{ isDragging ? 'Drop files here' : 'Click or drag files' }}
        </p>
        <input
          ref="fileInput"
          type="file"
          multiple
          class="hidden"
          @change="handleFileSelect"
          :disabled="loading"
        />
      </div>

      <!-- Upload Progress -->
      <div v-if="uploadProgress > 0 && uploadProgress < 100" class="mt-2">
        <div class="flex items-center justify-between text-xs text-blueGray-600 mb-1">
          <span>Uploading...</span>
          <span>{{ uploadProgress }}%</span>
        </div>
        <div class="w-full bg-blueGray-200 rounded-full h-1.5">
          <div
            class="bg-indigo-600 h-1.5 rounded-full transition-all duration-300"
            :style="{ width: `${uploadProgress}%` }"
          ></div>
        </div>
      </div>
    </div>

    <!-- Error Display -->
    <div v-if="error" class="px-3 py-2 bg-red-50 border-b border-red-200 flex-shrink-0">
      <div class="flex items-start gap-2">
        <i class="fas fa-exclamation-circle text-red-500 text-sm mt-0.5"></i>
        <div class="flex-1 min-w-0">
          <p class="text-xs text-red-700">{{ error }}</p>
        </div>
        <button
          @click="clearError"
          class="text-red-400 hover:text-red-600 transition-colors flex-shrink-0"
        >
          <i class="fas fa-times text-xs"></i>
        </button>
      </div>
    </div>

    <!-- File List -->
    <div class="flex-1 overflow-y-auto p-3 space-y-2" style="scrollbar-width: thin;">
      <!-- Empty State -->
      <EmptyState
        v-if="!hasFiles && !loading"
        icon="fas fa-folder-open"
        message="No files attached"
        compact
      />

      <!-- Loading State -->
      <div v-if="loading && !hasFiles" class="text-center py-8">
        <i class="fas fa-spinner fa-spin text-2xl text-blueGray-400 mb-2"></i>
        <p class="text-xs text-blueGray-500">Loading files...</p>
      </div>

      <!-- File Items -->
      <div
        v-for="file in sortedFiles"
        :key="file.file_id"
        class="file-item group p-2 bg-autobot-bg-card border rounded-lg hover:shadow-sm transition-all"
        :class="selectedFileIds.has(file.file_id)
          ? 'border-indigo-400 bg-indigo-50'
          : 'border-blueGray-200 hover:border-indigo-300'"
        @contextmenu="showContextMenu($event, file)"
      >
        <div class="flex items-start gap-2">
          <!-- Checkbox -->
          <input
            type="checkbox"
            :checked="selectedFileIds.has(file.file_id)"
            @change="toggleFileSelection(file.file_id)"
            class="mt-1 flex-shrink-0 rounded border-blueGray-300 text-indigo-600 focus:ring-indigo-500"
          />

          <!-- File Icon -->
          <div class="file-icon flex-shrink-0">
            <i :class="getFileIcon(file.mime_type)" class="text-blueGray-500 text-lg"></i>
          </div>

          <!-- File Info -->
          <div class="flex-1 min-w-0">
            <!-- Inline Rename -->
            <div v-if="renamingFileId === file.file_id" class="flex items-center gap-1">
              <input
                v-model="renameValue"
                @keyup.enter="handleRename"
                @keyup.escape="renamingFileId = null"
                class="w-full text-xs px-1 py-0.5 border border-indigo-400 rounded focus:outline-none"
              />
              <button @click="handleRename" class="action-btn" title="Save">
                <i class="fas fa-check text-xs text-green-600"></i>
              </button>
            </div>
            <p v-else class="text-xs font-medium text-blueGray-700 truncate" :title="file.filename">
              {{ file.filename }}
            </p>
            <div class="flex items-center gap-2 mt-0.5">
              <span class="text-xs text-blueGray-500">{{ formatFileSize(file.size_bytes) }}</span>
              <span class="text-xs text-blueGray-400">&middot;</span>
              <span class="text-xs text-blueGray-500">{{ formatDate(file.upload_timestamp) }}</span>
            </div>
            <StatusBadge
              v-if="file.file_type === 'generated'"
              variant="primary"
              size="small"
              class="mt-1"
            >
              AI Generated
            </StatusBadge>
          </div>

          <!-- File Actions -->
          <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
            <button
              v-if="isPreviewable(file.mime_type)"
              @click="handlePreview(file.file_id)"
              class="action-btn"
              title="Preview"
            >
              <i class="fas fa-eye text-xs"></i>
            </button>
            <button
              v-if="isEditable(file.mime_type)"
              @click="startEdit(file.file_id, file.filename)"
              class="action-btn"
              title="Edit"
            >
              <i class="fas fa-edit text-xs"></i>
            </button>
            <button
              @click="handleDownload(file.file_id, file.filename)"
              class="action-btn"
              title="Download"
            >
              <i class="fas fa-download text-xs"></i>
            </button>
            <button
              @click="handleDelete(file.file_id, file.filename)"
              class="action-btn text-red-400 hover:text-red-600"
              title="Delete"
            >
              <i class="fas fa-trash text-xs"></i>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Context Menu -->
    <Teleport to="body">
      <div
        v-if="contextMenu"
        class="fixed z-50 bg-autobot-bg-card border border-blueGray-200 rounded-lg shadow-lg py-1 min-w-[140px]"
        :style="{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }"
        @click.stop
      >
        <button v-if="isPreviewable(contextMenu.mimeType)" @click="handlePreview(contextMenu.fileId); closeContextMenu()"
          class="ctx-menu-item"><i class="fas fa-eye w-4"></i> Preview</button>
        <button v-if="isEditable(contextMenu.mimeType)" @click="startEdit(contextMenu.fileId, contextMenu.filename)"
          class="ctx-menu-item"><i class="fas fa-edit w-4"></i> Edit</button>
        <button @click="startRename(contextMenu.fileId, contextMenu.filename)"
          class="ctx-menu-item"><i class="fas fa-i-cursor w-4"></i> Rename</button>
        <button @click="handleCopy(contextMenu.fileId)"
          class="ctx-menu-item"><i class="fas fa-copy w-4"></i> Duplicate</button>
        <button @click="handleDownload(contextMenu.fileId, contextMenu.filename); closeContextMenu()"
          class="ctx-menu-item"><i class="fas fa-download w-4"></i> Download</button>
        <div class="border-t border-blueGray-200 my-1"></div>
        <button @click="handleDelete(contextMenu.fileId, contextMenu.filename); closeContextMenu()"
          class="ctx-menu-item text-red-600 hover:bg-red-50"><i class="fas fa-trash w-4"></i> Delete</button>
      </div>
    </Teleport>

    <!-- Create File Dialog -->
    <Teleport to="body">
      <div v-if="showCreateDialog" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40" @click.self="showCreateDialog = false">
        <div class="bg-autobot-bg-card rounded-lg shadow-xl w-80 p-4">
          <h4 class="text-sm font-semibold text-blueGray-700 mb-3">Create New File</h4>
          <input
            v-model="newFileName"
            placeholder="filename.txt"
            class="w-full text-xs px-2 py-1.5 border border-blueGray-200 rounded-md focus:outline-none focus:border-indigo-400 mb-2"
            @keyup.enter="handleCreateFile"
          />
          <textarea
            v-model="newFileContent"
            placeholder="File content (optional)"
            rows="4"
            class="w-full text-xs px-2 py-1.5 border border-blueGray-200 rounded-md focus:outline-none focus:border-indigo-400 mb-3 resize-none font-mono"
          ></textarea>
          <div class="flex justify-end gap-2">
            <button @click="showCreateDialog = false" class="px-3 py-1 text-xs text-blueGray-600 hover:bg-blueGray-100 rounded">Cancel</button>
            <button @click="handleCreateFile" :disabled="!newFileName.trim()" class="px-3 py-1 text-xs text-white bg-indigo-600 hover:bg-indigo-700 rounded disabled:opacity-50">Create</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Edit File Dialog -->
    <Teleport to="body">
      <div v-if="editingFileId" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40" @click.self="editingFileId = null">
        <div class="bg-autobot-bg-card rounded-lg shadow-xl w-[480px] max-h-[80vh] flex flex-col p-4">
          <div class="flex items-center justify-between mb-3">
            <h4 class="text-sm font-semibold text-blueGray-700 truncate">{{ editingFileName }}</h4>
            <button @click="editingFileId = null" class="action-btn"><i class="fas fa-times text-xs"></i></button>
          </div>
          <textarea
            v-model="editingContent"
            class="flex-1 w-full text-xs px-2 py-1.5 border border-blueGray-200 rounded-md focus:outline-none focus:border-indigo-400 resize-none font-mono min-h-[200px]"
          ></textarea>
          <div class="flex justify-end gap-2 mt-3">
            <button @click="editingFileId = null" class="px-3 py-1 text-xs text-blueGray-600 hover:bg-blueGray-100 rounded">Cancel</button>
            <button @click="handleSaveEdit" class="px-3 py-1 text-xs text-white bg-indigo-600 hover:bg-indigo-700 rounded">Save</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useConversationFiles, type SortField } from '@/composables/useConversationFiles'
import { formatTimeAgo } from '@/utils/formatHelpers'
import EmptyState from '@/components/ui/EmptyState.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'

const props = defineProps<{
  sessionId: string
}>()

defineEmits<{
  close: []
}>()

// File management composable
const {
  stats,
  loading,
  error,
  uploadProgress,
  hasFiles,
  totalSizeFormatted,
  sortedFiles,
  searchQuery,
  sortField,
  sortDirection,
  selectedCount,
  allSelected,
  selectedFileIds,
  loadFiles,
  uploadFiles,
  deleteFile,
  downloadFile,
  previewFile,
  createFile,
  renameFile,
  getFileContent,
  updateFileContent,
  copyFile,
  toggleFileSelection,
  selectAllFiles,
  deleteSelectedFiles,
  setSort,
  getFileIcon,
  formatFileSize,
  isPreviewable,
  isEditable,
  clearError
} = useConversationFiles(props.sessionId)

// Local state
const fileInput = ref<HTMLInputElement>()
const isDragging = ref(false)
const viewMode = ref<'list' | 'grid'>('list')
const showCreateDialog = ref(false)
const newFileName = ref('')
const newFileContent = ref('')
const editingFileId = ref<string | null>(null)
const editingContent = ref('')
const editingFileName = ref('')
const renamingFileId = ref<string | null>(null)
const renameValue = ref('')
const contextMenu = ref<{ x: number; y: number; fileId: string; filename: string; mimeType: string } | null>(null)

const sortOptions = [
  { field: 'name' as SortField, label: 'Name' },
  { field: 'date' as SortField, label: 'Date' },
  { field: 'size' as SortField, label: 'Size' },
  { field: 'type' as SortField, label: 'Type' }
]

// Methods
const triggerFileInput = () => {
  if (loading.value) return
  fileInput.value?.click()
}

const handleFileSelect = async (event: Event) => {
  const target = event.target as HTMLInputElement
  if (target.files && target.files.length > 0) {
    await uploadFiles(target.files)
    target.value = ''
  }
}

const handleDrop = async (event: DragEvent) => {
  isDragging.value = false
  if (event.dataTransfer?.files && event.dataTransfer.files.length > 0) {
    await uploadFiles(event.dataTransfer.files)
  }
}

const handlePreview = async (fileId: string) => { await previewFile(fileId) }
const handleDownload = async (fileId: string, filename: string) => { await downloadFile(fileId, filename) }
const handleDelete = async (fileId: string, filename: string) => {
  if (confirm(`Delete "${filename}"? This action cannot be undone.`)) {
    await deleteFile(fileId)
  }
}

// Issue #70: New file manager handlers
const handleCreateFile = async () => {
  if (!newFileName.value.trim()) return
  await createFile(newFileName.value.trim(), newFileContent.value)
  showCreateDialog.value = false
  newFileName.value = ''
  newFileContent.value = ''
}

const startRename = (fileId: string, currentName: string) => {
  renamingFileId.value = fileId
  renameValue.value = currentName
  contextMenu.value = null
}

const handleRename = async () => {
  if (!renamingFileId.value || !renameValue.value.trim()) return
  await renameFile(renamingFileId.value, renameValue.value.trim())
  renamingFileId.value = null
  renameValue.value = ''
}

const startEdit = async (fileId: string, filename: string) => {
  contextMenu.value = null
  const content = await getFileContent(fileId)
  if (content !== null) {
    editingFileId.value = fileId
    editingContent.value = content
    editingFileName.value = filename
  }
}

const handleSaveEdit = async () => {
  if (!editingFileId.value) return
  await updateFileContent(editingFileId.value, editingContent.value)
  editingFileId.value = null
  editingContent.value = ''
  editingFileName.value = ''
}

const handleCopy = async (fileId: string) => {
  contextMenu.value = null
  await copyFile(fileId)
}

const handleBulkDelete = async () => {
  if (confirm(`Delete ${selectedCount.value} selected files? This cannot be undone.`)) {
    await deleteSelectedFiles()
  }
}

const showContextMenu = (event: MouseEvent, file: { file_id: string; filename: string; mime_type: string }) => {
  event.preventDefault()
  contextMenu.value = {
    x: event.clientX,
    y: event.clientY,
    fileId: file.file_id,
    filename: file.filename,
    mimeType: file.mime_type
  }
}

const closeContextMenu = () => { contextMenu.value = null }

// Keyboard shortcuts
const handleKeydown = (event: KeyboardEvent) => {
  if (event.ctrlKey && event.key === 'n') {
    event.preventDefault()
    showCreateDialog.value = true
  }
  if (event.key === 'Escape') {
    if (contextMenu.value) { closeContextMenu(); return }
    if (showCreateDialog.value) { showCreateDialog.value = false; return }
    if (editingFileId.value) { editingFileId.value = null; return }
    if (renamingFileId.value) { renamingFileId.value = null; return }
  }
  if (event.key === 'Delete' && selectedCount.value > 0) {
    handleBulkDelete()
  }
}

// Use shared time formatting utility
const formatDate = formatTimeAgo

onMounted(() => {
  if (props.sessionId) loadFiles()
  document.addEventListener('keydown', handleKeydown)
  document.addEventListener('click', closeContextMenu)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
  document.removeEventListener('click', closeContextMenu)
})

watch(() => props.sessionId, (newSessionId) => {
  if (newSessionId) loadFiles()
})
</script>

<style scoped>
.chat-file-panel {
  width: 280px;
  max-width: 280px;
  min-width: 280px;
}

.action-btn {
  @apply w-6 h-6 flex items-center justify-center rounded transition-colors text-blueGray-400 hover:text-blueGray-600 hover:bg-blueGray-100;
}

.ctx-menu-item {
  @apply w-full text-left px-3 py-1.5 text-xs text-blueGray-700 hover:bg-blueGray-100 flex items-center gap-2 transition-colors;
}

/* Issue #704: Migrated to CSS design tokens */
/* Scrollbar styling */
.overflow-y-auto::-webkit-scrollbar {
  width: 6px;
}

.overflow-y-auto::-webkit-scrollbar-track {
  background: var(--bg-secondary);
}

.overflow-y-auto::-webkit-scrollbar-thumb {
  background: var(--border-default);
  border-radius: var(--radius-sm);
}

.overflow-y-auto::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary);
}

/* File item animations */
.file-item {
  animation: slideInFromRight 0.2s ease-out;
}

@keyframes slideInFromRight {
  from {
    opacity: 0;
    transform: translateX(10px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}
</style>
