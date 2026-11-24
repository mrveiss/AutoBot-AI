<template>
  <BaseCard class="content-pane" flush :aria-label="$t('knowledge.contentViewer.label')">
    <div v-if="!selectedFile" class="placeholder-state">
      <Icon name="file-alt" />
      <h4>{{ $t('knowledge.contentViewer.noFileSelected') }}</h4>
      <p>{{ $t('knowledge.contentViewer.selectFileHint') }}</p>
    </div>

    <article v-else class="file-viewer">
      <header class="file-header">
        <span class="tile" aria-hidden="true"><Icon :name="fileIcon" /></span>
        <div class="file-info">
          <h2 class="file-title">{{ displayName }}</h2>
          <span class="file-meta">{{ metaLine }}</span>
        </div>
        <BaseTooltip :text="$t('knowledge.contentViewer.closeFileViewer')" placement="left">
          <template #default="{ describedby }">
            <BaseButton
              variant="ghost"
              size="sm"
              :aria-label="$t('knowledge.contentViewer.closeFileViewer')"
              :aria-describedby="describedby"
              @click="$emit('close')"
            >
              <Icon name="times" aria-hidden="true" />
            </BaseButton>
          </template>
        </BaseTooltip>
      </header>

      <div class="file-content">
        <div v-if="isLoading" class="loading-content" role="status">
          <BaseSpinner size="sm" />
          <p>{{ $t('knowledge.contentViewer.loadingContent') }}</p>
        </div>
        <div v-else-if="error" class="error-content" role="alert">
          <Icon name="exclamation-circle" />
          <p>{{ error }}</p>
        </div>
        <pre v-else class="content-display">{{ content }}</pre>
      </div>

      <footer v-if="tags.length" class="file-tags">
        <span v-for="tag in tags" :key="tag" class="tag">#{{ tag }}</span>
      </footer>
    </article>
  </BaseCard>
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

import type { IconName } from '@/components/ui/Icon.vue'
import Icon from '@/components/ui/Icon.vue'
import { computed } from 'vue'
import { BaseButton, BaseCard, BaseSpinner, BaseTooltip } from '@autobot/ui'
import { useKnowledgeIcons } from '@/composables/knowledge/useKnowledgeIcons'
import { formatCategoryName, formatDate, formatFileSize, formatManPageTitle, knowledgeNodeFactType } from '@/utils/formatHelpers'
import { useI18n } from 'vue-i18n'

interface TreeNode {
  id: string
  name: string
  type: 'file' | 'folder'
  path?: string
  size?: number
  date?: string
  category?: string
  metadata?: Record<string, unknown>
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

const { getFileIcon: getFileIconUtil } = useKnowledgeIcons()
const { t } = useI18n()

// #21037: display-only man-page label; selectedFile.name stays raw.
const displayName = computed(() =>
  formatManPageTitle(props.selectedFile?.name, knowledgeNodeFactType(props.selectedFile?.metadata), t),
)

// The fact's own tags (metadata.tags), when the backend stored any.
const tags = computed<string[]>(() => {
  const raw = props.selectedFile?.metadata?.tags
  return Array.isArray(raw) ? raw.filter((tag): tag is string => typeof tag === 'string') : []
})

const metaLine = computed(() => {
  const file = props.selectedFile
  if (!file) return ''
  const parts = [file.category ? formatCategoryName(file.category) : '', formatFileSize(file.size || 0)]
  if (file.date) parts.push(formatDate(file.date))
  return parts.filter(Boolean).join(' · ')
})

const fileIcon = computed<IconName>(() => {
  if (!props.selectedFile) return 'file'
  // #9724: getFileIcon expects the file NAME — passing the whole TreeNode
  // always fell through to the generic 'file' icon.
  return getFileIconUtil(props.selectedFile.name, props.selectedFile.type === 'folder')
})
</script>

<style scoped>
.content-pane {
  display: flex;
  flex-direction: column;
  min-inline-size: 0;
}

.placeholder-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  padding: var(--spacing-8) var(--spacing-4);
  text-align: center;
  color: var(--muted);
}

.placeholder-state h4,
.placeholder-state p {
  margin: 0;
}

.file-viewer {
  display: flex;
  flex-direction: column;
  min-block-size: 0;
  flex: 1;
}

.file-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3) var(--spacing-4);
  border-block-end: var(--bw) solid var(--line);
}

.tile {
  display: grid;
  place-items: center;
  inline-size: 34px;
  block-size: 34px;
  flex: none;
  border-radius: var(--radius-lg);
  background: var(--tile);
  border: var(--bw) solid var(--tile-b);
  color: var(--stroke);
}

.file-info {
  display: flex;
  flex-direction: column;
  gap: 1px;
  flex: 1;
  min-inline-size: 0;
}

.file-title {
  margin: 0;
  font-family: var(--font-mono);
  font-size: var(--text-base);
  font-weight: 500;
  color: var(--text);
  overflow-wrap: anywhere;
}

.file-meta {
  font-size: var(--text-sm);
  color: var(--muted);
}

.file-content {
  flex: 1;
  min-block-size: 0;
  overflow: auto;
  padding: var(--spacing-3) var(--spacing-4);
}

.content-display {
  margin: 0;
  font-family: var(--font-sans);
  font-size: var(--text-base);
  line-height: 1.6;
  color: var(--text);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.loading-content,
.error-content {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  color: var(--muted);
}

.error-content {
  color: var(--bad-fg);
}

.file-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-4);
  border-block-start: var(--bw) solid var(--line);
}

.tag {
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-md);
  background: var(--surface2);
  border: var(--bw) solid var(--border);
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--text2);
}
</style>
