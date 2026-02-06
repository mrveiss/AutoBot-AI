<template>
  <div
    v-if="showPreview && previewFile"
    class="file-preview-modal"
    @click="$emit('close')"
    @keyup.escape="$emit('close')"
    tabindex="0"
  >
    <div class="modal-content" @click.stop>
      <!-- Modal Header -->
      <div class="modal-header">
        <h3>{{ previewFile.name }}</h3>
        <button
          class="close-btn"
          @click="$emit('close')"
          aria-label="Close preview"
        >
          &times;
        </button>
      </div>

      <!-- Modal Body -->
      <div class="modal-body">
        <!-- HTML File Preview -->
        <div v-if="previewFile.type === 'html'" class="html-preview">
          <iframe
            :src="previewFile.url"
            class="preview-frame"
            sandbox="allow-same-origin allow-scripts"
            title="HTML Preview"
          ></iframe>
        </div>

        <!-- Image Preview -->
        <div v-else-if="previewFile.type === 'image'" class="image-preview">
          <img
            :src="previewFile.url"
            :alt="previewFile.name"
            class="preview-image"
          />
        </div>

        <!-- Text/Code Preview -->
        <div v-else-if="previewFile.type === 'text'" class="text-preview">
          <pre><code>{{ previewFile.content }}</code></pre>
        </div>

        <!-- JSON Preview -->
        <div v-else-if="previewFile.type === 'json'" class="json-preview">
          <pre><code>{{ formatJson(previewFile.content || '') }}</code></pre>
        </div>

        <!-- PDF Preview -->
        <div v-else-if="previewFile.type === 'pdf'" class="pdf-preview">
          <iframe
            :src="previewFile.url"
            class="preview-frame"
            title="PDF Preview"
          ></iframe>
        </div>

        <!-- Other file types -->
        <div v-else class="file-info">
          <div class="info-item">
            <strong>File:</strong> {{ previewFile.name }}
          </div>
          <div class="info-item">
            <strong>Type:</strong> {{ previewFile.fileType }}
          </div>
          <div class="info-item">
            <strong>Size:</strong> {{ formatSize(previewFile.size) }}
          </div>
          <p class="no-preview-message">
            This file type cannot be previewed directly.
          </p>
          <button
            @click="downloadFile"
            class="download-btn"
          >
            <i class="fas fa-download"></i>
            Download File
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface FilePreviewData {
  name: string
  type: string
  url?: string
  content?: string
  fileType?: string
  size?: number
}

interface Props {
  showPreview: boolean
  previewFile: FilePreviewData | null
}

interface Emits {
  (e: 'close'): void
  (e: 'download', file: FilePreviewData): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// Methods
const formatJson = (content: string): string => {
  try {
    return JSON.stringify(JSON.parse(content), null, 2)
  } catch {
    return content
  }
}

const formatSize = (bytes: number = 0): string => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

const downloadFile = () => {
  if (props.previewFile) {
    emit('download', props.previewFile)
  }
}
</script>

<style scoped>
.file-preview-modal {
  @apply fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50;
}

.modal-content {
  @apply bg-white rounded-lg shadow-xl max-w-4xl max-h-[90vh] w-full mx-4 overflow-hidden;
}

.modal-header {
  @apply flex justify-between items-center p-4 border-b border-gray-200 bg-gray-50;
}

.modal-header h3 {
  @apply text-lg font-semibold text-gray-900 truncate;
}

.close-btn {
  @apply text-gray-400 hover:text-gray-600 text-2xl font-bold leading-none p-1;
}

.modal-body {
  @apply p-4 overflow-auto max-h-[calc(90vh-80px)];
}

/* Preview styles */
.preview-frame {
  @apply w-full h-96 border border-gray-200 rounded;
}

.preview-image {
  @apply max-w-full h-auto rounded shadow-md;
}

.text-preview,
.json-preview {
  @apply bg-gray-100 rounded p-4 overflow-auto max-h-96;
}

.text-preview code,
.json-preview code {
  @apply text-sm font-mono;
}

.file-info {
  @apply text-center py-8;
}

.info-item {
  @apply mb-2 text-sm;
}

.no-preview-message {
  @apply text-gray-600 mt-4 mb-6;
}

.download-btn {
  @apply px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 inline-flex items-center gap-2;
}
</style>
