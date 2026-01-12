<template>
  <div class="chat-file-panel h-full flex flex-col bg-white border-l border-blueGray-200">
    <!-- Header -->
    <div class="flex items-center justify-between p-3 border-b border-blueGray-200 flex-shrink-0">
      <div class="flex items-center gap-2">
        <i class="fas fa-paperclip text-blueGray-600"></i>
        <h3 class="text-sm font-semibold text-blueGray-700">Files</h3>
      </div>
      <button
        @click="$emit('close')"
        class="text-blueGray-400 hover:text-blueGray-600 transition-colors p-1 rounded"
        title="Close panel"
      >
        <i class="fas fa-times"></i>
      </button>
    </div>

    <!-- File Statistics -->
    <div v-if="stats.total_files > 0" class="px-3 py-2 bg-blueGray-50 border-b border-blueGray-200 flex-shrink-0">
      <div class="flex justify-between text-xs text-blueGray-600">
        <span>{{ stats.total_files }} file{{ stats.total_files > 1 ? 's' : '' }}</span>
        <span>{{ totalSizeFormatted }}</span>
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
        v-for="file in files"
        :key="file.file_id"
        class="file-item group p-2 bg-white border border-blueGray-200 rounded-lg hover:border-indigo-300 hover:shadow-sm transition-all"
      >
        <div class="flex items-start gap-2">
          <!-- File Icon -->
          <div class="file-icon flex-shrink-0">
            <i :class="getFileIcon(file.mime_type)" class="text-blueGray-500 text-lg"></i>
          </div>

          <!-- File Info -->
          <div class="flex-1 min-w-0">
            <p class="text-xs font-medium text-blueGray-700 truncate" :title="file.filename">
              {{ file.filename }}
            </p>
            <div class="flex items-center gap-2 mt-0.5">
              <span class="text-xs text-blueGray-500">{{ formatFileSize(file.size_bytes) }}</span>
              <span class="text-xs text-blueGray-400">•</span>
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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useConversationFiles } from '@/composables/useConversationFiles'
import { formatTimeAgo } from '@/utils/formatHelpers'
import EmptyState from '@/components/ui/EmptyState.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'

const props = defineProps<{
  sessionId: string
}>()

const emit = defineEmits<{
  close: []
}>()

// File management composable
const {
  files,
  stats,
  loading,
  error,
  uploadProgress,
  hasFiles,
  totalSizeFormatted,
  loadFiles,
  uploadFiles,
  deleteFile,
  downloadFile,
  previewFile,
  getFileIcon,
  formatFileSize,
  isPreviewable,
  clearError
} = useConversationFiles(props.sessionId)

// Local state
const fileInput = ref<HTMLInputElement>()
const isDragging = ref(false)

// Methods
const triggerFileInput = () => {
  if (loading.value) return
  fileInput.value?.click()
}

const handleFileSelect = async (event: Event) => {
  const target = event.target as HTMLInputElement
  if (target.files && target.files.length > 0) {
    await uploadFiles(target.files)
    // Reset input to allow re-uploading same file
    target.value = ''
  }
}

const handleDrop = async (event: DragEvent) => {
  isDragging.value = false

  if (event.dataTransfer?.files && event.dataTransfer.files.length > 0) {
    await uploadFiles(event.dataTransfer.files)
  }
}

const handlePreview = async (fileId: string) => {
  await previewFile(fileId)
}

const handleDownload = async (fileId: string, filename: string) => {
  await downloadFile(fileId, filename)
}

const handleDelete = async (fileId: string, filename: string) => {
  if (confirm(`Delete "${filename}"? This action cannot be undone.`)) {
    await deleteFile(fileId)
  }
}

// Use shared time formatting utility
const formatDate = formatTimeAgo

// Load files on mount and when session changes
onMounted(() => {
  if (props.sessionId) {
    loadFiles()
  }
})

watch(() => props.sessionId, (newSessionId) => {
  if (newSessionId) {
    loadFiles()
  }
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
