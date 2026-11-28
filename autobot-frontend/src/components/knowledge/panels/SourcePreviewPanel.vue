<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<script setup lang="ts">
/**
 * Source Preview Panel Component (Issue #747)
 *
 * Side panel for previewing source documents from chat.
 * Features:
 * - Document title and metadata
 * - Full content preview with markdown rendering
 * - "Open in Knowledge Manager" button (deep-link)
 * - "Copy content" button
 * - Resizable width
 * - Slide animation
 */

import type { IconName } from '@/components/ui/Icon.vue'
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, watch, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { BaseButton, BaseDrawer } from '@autobot/ui'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('SourcePreviewPanel')

// =============================================================================
// Type Definitions
// =============================================================================

export interface SourceDocument {
  id: string
  title: string
  content: string
  path?: string
  type?: string
  category?: string
  score?: number
  metadata?: {
    wordCount?: number
    lastModified?: string
    source?: string
  }
}

// =============================================================================
// Props & Emits
// =============================================================================

const props = defineProps<{
  modelValue: boolean
  document: SourceDocument | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'openInKnowledgeManager', doc: SourceDocument): void
}>()

// =============================================================================
// State
// =============================================================================

const router = useRouter()
const panelWidth = ref(400)
const isResizing = ref(false)
const copySuccess = ref(false)
// The "Copied" feedback timer; cleared on unmount and when the document changes (#19145 review).
let copyTimer: ReturnType<typeof setTimeout> | null = null
const clearCopyTimer = (): void => { if (copyTimer) clearTimeout(copyTimer); copyTimer = null }

// =============================================================================
// Computed
// =============================================================================

const isOpen = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
})

const hasDocument = computed(() => props.document !== null)

const wordCount = computed(() => {
  if (!props.document?.content) return 0
  return props.document.content.split(/\s+/).filter(Boolean).length
})

const relevancePercent = computed(() => {
  if (!props.document?.score) return null
  return Math.round(props.document.score * 100)
})

// =============================================================================
// Methods
// =============================================================================

function closePanel(): void {
  isOpen.value = false
}

async function copyContent(): Promise<void> {
  if (!props.document?.content) return

  try {
    await navigator.clipboard.writeText(props.document.content)
    copySuccess.value = true
    clearCopyTimer()
    copyTimer = setTimeout(() => {
      copySuccess.value = false
      copyTimer = null
    }, 2000)
  } catch (err) {
    logger.error('Failed to copy content:', err)
  }
}

function openInKnowledgeManager(): void {
  if (!props.document) return

  // Navigate to Knowledge Manager with document pre-selected
  router.push({
    path: '/knowledge',
    query: {
      tab: 'system-docs',
      doc: props.document.id
    }
  })

  emit('openInKnowledgeManager', props.document)
  closePanel()
}

// Resize handling
function startResize(event: MouseEvent): void {
  isResizing.value = true
  document.addEventListener('mousemove', handleResize)
  document.addEventListener('mouseup', stopResize)
  event.preventDefault()
}

function handleResize(event: MouseEvent): void {
  if (!isResizing.value) return

  const newWidth = window.innerWidth - event.clientX
  panelWidth.value = Math.max(300, Math.min(800, newWidth))
}

function stopResize(): void {
  isResizing.value = false
  document.removeEventListener('mousemove', handleResize)
  document.removeEventListener('mouseup', stopResize)
}

function getTypeIcon(type?: string): IconName {
  const icons: Record<string, IconName> = {
    'markdown': 'file-alt',
    'document': 'file-alt',
    'api': 'code',
    'code': 'code',
    'guide': 'book',
    'reference': 'book-open'
  }
  return icons[type || 'document'] || 'file'
}

// Another document resets the copy feedback instead of inheriting it.
watch(() => props.document?.id, () => { clearCopyTimer(); copySuccess.value = false })

// Cleanup on close
watch(() => props.modelValue, (isOpen) => {
  if (!isOpen) {
    document.removeEventListener('mousemove', handleResize)
    document.removeEventListener('mouseup', stopResize)
  }
})

// #2849: Ensure resize listeners are removed if component unmounts mid-resize
onUnmounted(() => {
  clearCopyTimer()
  document.removeEventListener('mousemove', handleResize)
  document.removeEventListener('mouseup', stopResize)
})
</script>

<template>
  <!-- Kit BaseDrawer (#14780); the width stays user-resizable through the handle below. -->
  <BaseDrawer
    v-model="isOpen"
    :title="document?.title || $t('knowledge.panels.sourcePreview.defaultTitle')"
    :width="panelWidth"
    flush
    :close-label="$t('knowledge.panels.sourcePreview.closePanel')"
  >
    <template #title>
      <span class="doc-type-icon" aria-hidden="true"><Icon :name="getTypeIcon(document?.type)" /></span>
      {{ document?.title || $t('knowledge.panels.sourcePreview.defaultTitle') }}
    </template>
    <template v-if="document?.path" #subtitle>
      <span class="panel-path">{{ document.path }}</span>
    </template>

    <div class="resize-handle" @mousedown="startResize"></div>
    <div class="panel-body">
      <div v-if="!hasDocument" class="empty-state">
        <Icon name="file-alt" />
        <p>{{ $t('knowledge.panels.sourcePreview.noDocument') }}</p>
      </div>

      <template v-else>
        <!-- Metadata Bar -->
        <div class="metadata-bar">
          <span v-if="document?.category" class="meta-item">
            <Icon name="folder" />
            {{ document.category }}
          </span>
          <span class="meta-item">
            <Icon name="file-word" />
            {{ $t('knowledge.panels.sourcePreview.wordCount', { count: wordCount }) }}
          </span>
          <span v-if="relevancePercent !== null" class="meta-item relevance">
            <Icon name="bullseye" />
            {{ $t('knowledge.panels.sourcePreview.relevance', { percent: relevancePercent }) }}
          </span>
        </div>

        <!-- Content -->
        <div class="content-area">
          <pre class="source-content">{{ document?.content }}</pre>
        </div>
      </template>
    </div>

    <template #actions>
      <div class="panel-footer">
          <BaseButton
            variant="outline"
            size="sm"
            :class="{ success: copySuccess }"
            @click="copyContent"
            :disabled="!hasDocument"
          >
            <Icon :name="copySuccess ? 'check' : 'copy'" />
            {{ copySuccess ? $t('knowledge.panels.sourcePreview.copied') : $t('knowledge.panels.sourcePreview.copy') }}
          </BaseButton>

          <BaseButton
            variant="primary"
            size="sm"
            @click="openInKnowledgeManager"
            :disabled="!hasDocument"
          >
            <Icon name="external-link-alt" />
            {{ $t('knowledge.panels.sourcePreview.openInKnowledgeManager') }}
          </BaseButton>
      </div>
    </template>
  </BaseDrawer>
</template>

<style scoped>
/* Resize Handle */
.resize-handle {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  cursor: ew-resize;
  background: transparent;
  transition: background var(--duration-150);
  z-index: var(--z-10);
}

.resize-handle:hover,
.resize-handle:active {
  background: var(--color-info);
}

/* Header */


.doc-type-icon {
  width: 2.5rem;
  height: 2.5rem;
  display: inline-flex;
  vertical-align: middle;
  margin-right: var(--spacing-3);
  align-items: center;
  justify-content: center;
  background: var(--color-info-bg);
  color: var(--color-info);
  border-radius: var(--radius-lg);
  font-size: var(--text-lg);
  flex-shrink: 0;
}



.panel-path {
  display: block;
  font-size: var(--text-xs);
  color: var(--text-muted);
  font-family: var(--font-mono);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}



/* Body */
.panel-body {
  min-height: 100%;
  display: flex;
  flex-direction: column;
}

.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  gap: var(--spacing-3);
}

.empty-state .icon {
  width: 2.5rem;
  height: 2.5rem;
  opacity: 0.5;
}

/* Metadata Bar */
.metadata-bar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-4);
  padding: var(--spacing-3) var(--spacing-6);
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
}

.meta-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.meta-item .icon {
  color: var(--text-muted);
}

.meta-item.relevance {
  color: var(--color-success);
}

.meta-item.relevance .icon {
  color: var(--color-success);
}

/* Content */
.content-area {
  flex: 1;
  padding: var(--spacing-6);
  overflow-y: auto;
}

.source-content {
  font-family: var(--font-mono);
  font-size: 0.8125rem;
  line-height: 1.7;
  white-space: pre-wrap;
  word-wrap: break-word;
  margin: var(--spacing-0);
  color: var(--text-primary);
}

/* Footer */
.panel-footer {
  display: flex;
  justify-content: space-between;
  gap: var(--spacing-3);
  width: 100%;
}

.panel-footer .success {
  color: var(--color-success);
  border-color: var(--color-success);
}


/* Responsive */
@media (max-width: 768px) {
  .resize-handle {
    display: none;
  }
}
</style>
