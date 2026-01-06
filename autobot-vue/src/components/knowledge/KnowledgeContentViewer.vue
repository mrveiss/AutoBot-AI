<template>
  <div class="content-pane">
    <div v-if="!selectedFile" class="placeholder-state">
      <i class="fas fa-file-alt"></i>
      <h4>No file selected</h4>
      <p>Select a file from the tree to view its contents</p>
    </div>

    <div v-else class="file-viewer">
      <div class="file-header">
        <div class="file-info">
          <i :class="fileIcon"></i>
          <div>
            <h4>{{ selectedFile.name }}</h4>
            <p class="file-meta">
              {{ selectedFile.type }} • {{ formatFileSize(selectedFile.size || 0) }}
              <span v-if="selectedFile.date"> • {{ formatDate(selectedFile.date) }}</span>
            </p>
          </div>
        </div>
        <BaseButton
          variant="ghost"
          size="sm"
          @click="$emit('close')"
          class="close-btn"
          aria-label="Close file viewer"
        >
          <i class="fas fa-times"></i>
        </BaseButton>
      </div>

      <div class="file-content">
        <div v-if="isLoading" class="loading-content">
          <i class="fas fa-spinner fa-spin"></i>
          <p>Loading content...</p>
        </div>

        <div v-else-if="error" class="error-content">
          <i class="fas fa-exclamation-circle"></i>
          <p>{{ error }}</p>
        </div>

        <pre v-else class="content-display">{{ content }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Knowledge Content Viewer Component
 *
 * Displays the content of a selected knowledge file.
 * Extracted from KnowledgeBrowser.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import { computed } from 'vue'
import BaseButton from '@/components/base/BaseButton.vue'
import { useKnowledgeBase } from '@/composables/useKnowledgeBase'

interface TreeNode {
  id: string
  name: string
  type: 'file' | 'folder'
  path?: string
  size?: number
  date?: string
  category?: string
  metadata?: any
  content?: string
  children?: TreeNode[]
}

interface Props {
  selectedFile: TreeNode | null
  content: string
  isLoading?: boolean
  error?: string | null
}

interface Emits {
  (e: 'close'): void
}

const props = withDefaults(defineProps<Props>(), {
  isLoading: false,
  error: null
})

defineEmits<Emits>()

const { formatFileSize, formatDateOnly: formatDate, getFileIcon: getFileIconUtil } = useKnowledgeBase()

const fileIcon = computed(() => {
  if (!props.selectedFile) return 'fas fa-file'
  return getFileIconUtil(props.selectedFile as any)
})
</script>

<style scoped>
.content-pane {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: white;
  border-left: 1px solid #e2e8f0;
}

.placeholder-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem;
  text-align: center;
  color: #94a3b8;
}

.placeholder-state i {
  font-size: 3rem;
  margin-bottom: 1rem;
  opacity: 0.5;
}

.placeholder-state h4 {
  font-size: 1.125rem;
  font-weight: 600;
  color: #64748b;
  margin-bottom: 0.5rem;
}

.placeholder-state p {
  font-size: 0.875rem;
  color: #94a3b8;
}

.file-viewer {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.file-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.5rem;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
}

.file-info {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.file-info i {
  font-size: 1.5rem;
  color: #3b82f6;
}

.file-info h4 {
  font-size: 1rem;
  font-weight: 600;
  color: #1e293b;
  margin: 0;
}

.file-meta {
  font-size: 0.75rem;
  color: #64748b;
  margin: 0.25rem 0 0 0;
}

.close-btn {
  color: #64748b;
}

.close-btn:hover {
  color: #1e293b;
  background: #e2e8f0;
}

.file-content {
  flex: 1;
  overflow: auto;
  padding: 1.5rem;
}

.loading-content,
.error-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #64748b;
}

.loading-content i,
.error-content i {
  font-size: 2rem;
  margin-bottom: 1rem;
}

.error-content {
  color: #ef4444;
}

.content-display {
  margin: 0;
  padding: 1rem;
  background: #f8fafc;
  border-radius: 0.5rem;
  font-family: 'Fira Code', 'Monaco', 'Consolas', monospace;
  font-size: 0.875rem;
  line-height: 1.6;
  color: #334155;
  white-space: pre-wrap;
  word-wrap: break-word;
  overflow-x: auto;
}
</style>
