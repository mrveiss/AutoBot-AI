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
/* Issue #704: Migrated to CSS design tokens */
.content-pane {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
  border-left: 1px solid var(--border-default);
}

.placeholder-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-8);
  text-align: center;
  color: var(--text-tertiary);
}

.placeholder-state i {
  font-size: var(--text-4xl);
  margin-bottom: var(--spacing-4);
  opacity: 0.5;
}

.placeholder-state h4 {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2);
}

.placeholder-state p {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
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
  padding: var(--spacing-4) var(--spacing-6);
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
}

.file-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
}

.file-info i {
  font-size: var(--text-2xl);
  color: var(--color-primary);
}

.file-info h4 {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0;
}

.file-meta {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin: var(--spacing-1) 0 0 0;
}

.close-btn {
  color: var(--text-secondary);
}

.close-btn:hover {
  color: var(--text-primary);
  background: var(--bg-tertiary);
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
  color: var(--text-secondary);
}

.loading-content i,
.error-content i {
  font-size: var(--text-3xl);
  margin-bottom: var(--spacing-4);
}

.error-content {
  color: var(--color-error);
}

.content-display {
  margin: 0;
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  line-height: var(--leading-relaxed);
  color: var(--text-primary);
  white-space: pre-wrap;
  word-wrap: break-word;
  overflow-x: auto;
}
</style>
