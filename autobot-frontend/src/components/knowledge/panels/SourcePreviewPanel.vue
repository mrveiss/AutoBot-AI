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
import BaseButton from '@/components/base/BaseButton.vue'
import { createLogger } from '@/utils/debugUtils'
import { useI18n } from 'vue-i18n'

const logger = createLogger('SourcePreviewPanel')
const { t } = useI18n()

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
    setTimeout(() => {
      copySuccess.value = false
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

// Cleanup on close
watch(() => props.modelValue, (isOpen) => {
  if (!isOpen) {
    document.removeEventListener('mousemove', handleResize)
    document.removeEventListener('mouseup', stopResize)
  }
})

// #2849: Ensure resize listeners are removed if component unmounts mid-resize
onUnmounted(() => {
  document.removeEventListener('mousemove', handleResize)
  document.removeEventListener('mouseup', stopResize)
})
</script>

<template>
  <Teleport to="body">
    <Transition name="panel">
      <div
        v-if="isOpen"
        class="source-preview-overlay"
        @click.self="closePanel"
      >
        <aside
          class="source-preview-panel"
          :style="{ width: `${panelWidth}px` }"
        >
          <!-- Resize Handle -->
          <div
            class="resize-handle"
            @mousedown="startResize"
          ></div>

          <!-- Panel Header -->
          <header class="panel-header">
            <div class="header-content">
              <div class="doc-type-icon">
                <Icon :name="getTypeIcon(document?.type)" />
              </div>
              <div class="header-info">
                <h3 class="panel-title">{{ document?.title || $t('knowledge.panels.sourcePreview.defaultTitle') }}</h3>
                <span v-if="document?.path" class="panel-path">{{ document.path }}</span>
              </div>
            </div>
            <button
              class="close-btn"
              @click="closePanel"
              :title="$t('knowledge.panels.sourcePreview.closePanel')"
            >
              <Icon name="times" />
            </button>
          </header>

          <!-- Panel Content -->
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

          <!-- Panel Footer -->
          <footer class="panel-footer">
            <BaseButton
              variant="outline-solid"
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
          </footer>
        </aside>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* Overlay */
.source-preview-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.3);
  z-index: var(--z-modal);
  display: flex;
  justify-content: flex-end;
}

/* Panel */
.source-preview-panel {
  height: 100%;
  background: var(--bg-card);
  box-shadow: var(--shadow-2xl);
  display: flex;
  flex-direction: column;
  position: relative;
}

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
  z-index: 10;
}

.resize-handle:hover,
.resize-handle:active {
  background: var(--color-info);
}

/* Header */
.panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: var(--spacing-5) var(--spacing-6);
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
}

.header-content {
  display: flex;
  gap: var(--spacing-3-5);
  flex: 1;
  min-width: 0;
}

.doc-type-icon {
  width: 2.5rem;
  height: 2.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-info-bg);
  color: var(--color-info);
  border-radius: var(--radius-lg);
  font-size: var(--text-lg);
  flex-shrink: 0;
}

.header-info {
  flex: 1;
  min-width: 0;
}

.panel-title {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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

.close-btn {
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: none;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius-md);
  transition: all var(--duration-150);
  flex-shrink: 0;
}

.close-btn:hover {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

/* Body */
.panel-body {
  flex: 1;
  overflow-y: auto;
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

.empty-state i {
  font-size: 2.5rem;
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

.meta-item i {
  color: var(--text-muted);
}

.meta-item.relevance {
  color: var(--color-success);
}

.meta-item.relevance i {
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
  padding: var(--spacing-4) var(--spacing-6);
  border-top: 1px solid var(--border-default);
  background: var(--bg-card);
}

.panel-footer .success {
  color: var(--color-success);
  border-color: var(--color-success);
}

/* Transition */
.panel-enter-active,
.panel-leave-active {
  transition: opacity var(--duration-200) var(--ease-out);
}

.panel-enter-active .source-preview-panel,
.panel-leave-active .source-preview-panel {
  transition: transform var(--duration-200) var(--ease-out);
}

.panel-enter-from,
.panel-leave-to {
  opacity: 0;
}

.panel-enter-from .source-preview-panel,
.panel-leave-to .source-preview-panel {
  transform: translateX(100%);
}

/* Responsive */
@media (max-width: 768px) {
  .source-preview-panel {
    width: 100% !important;
    max-width: none;
  }

  .resize-handle {
    display: none;
  }
}
</style>
