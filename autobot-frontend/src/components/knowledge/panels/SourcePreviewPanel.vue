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

import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import BaseButton from '@/components/base/BaseButton.vue'
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

function getTypeIcon(type?: string): string {
  const icons: Record<string, string> = {
    'markdown': 'fas fa-file-alt',
    'document': 'fas fa-file-alt',
    'api': 'fas fa-code',
    'code': 'fas fa-code',
    'guide': 'fas fa-book',
    'reference': 'fas fa-book-open'
  }
  return icons[type || 'document'] || 'fas fa-file'
}

// Cleanup on unmount
watch(() => props.modelValue, (isOpen) => {
  if (!isOpen) {
    document.removeEventListener('mousemove', handleResize)
    document.removeEventListener('mouseup', stopResize)
  }
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
                <i :class="getTypeIcon(document?.type)"></i>
              </div>
              <div class="header-info">
                <h3 class="panel-title">{{ document?.title || 'Source Document' }}</h3>
                <span v-if="document?.path" class="panel-path">{{ document.path }}</span>
              </div>
            </div>
            <button
              class="close-btn"
              @click="closePanel"
              title="Close panel"
            >
              <i class="fas fa-times"></i>
            </button>
          </header>

          <!-- Panel Content -->
          <div class="panel-body">
            <div v-if="!hasDocument" class="empty-state">
              <i class="fas fa-file-alt"></i>
              <p>No document selected</p>
            </div>

            <template v-else>
              <!-- Metadata Bar -->
              <div class="metadata-bar">
                <span v-if="document?.category" class="meta-item">
                  <i class="fas fa-folder"></i>
                  {{ document.category }}
                </span>
                <span class="meta-item">
                  <i class="fas fa-file-word"></i>
                  {{ wordCount }} words
                </span>
                <span v-if="relevancePercent !== null" class="meta-item relevance">
                  <i class="fas fa-bullseye"></i>
                  {{ relevancePercent }}% relevant
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
              variant="outline"
              size="sm"
              :class="{ success: copySuccess }"
              @click="copyContent"
              :disabled="!hasDocument"
            >
              <i :class="copySuccess ? 'fas fa-check' : 'fas fa-copy'"></i>
              {{ copySuccess ? 'Copied!' : 'Copy' }}
            </BaseButton>

            <BaseButton
              variant="primary"
              size="sm"
              @click="openInKnowledgeManager"
              :disabled="!hasDocument"
            >
              <i class="fas fa-external-link-alt"></i>
              Open in Knowledge Manager
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
  z-index: 1000;
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
  transition: background 0.15s;
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
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
}

.header-content {
  display: flex;
  gap: 0.875rem;
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
  border-radius: 0.5rem;
  font-size: 1.125rem;
  flex-shrink: 0;
}

.header-info {
  flex: 1;
  min-width: 0;
}

.panel-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 0.25rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.panel-path {
  display: block;
  font-size: 0.75rem;
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
  border-radius: 0.375rem;
  transition: all 0.15s;
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
  gap: 0.75rem;
}

.empty-state i {
  font-size: 2.5rem;
  opacity: 0.5;
}

/* Metadata Bar */
.metadata-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  padding: 0.75rem 1.5rem;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.75rem;
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
  padding: 1.5rem;
  overflow-y: auto;
}

.source-content {
  font-family: var(--font-mono);
  font-size: 0.8125rem;
  line-height: 1.7;
  white-space: pre-wrap;
  word-wrap: break-word;
  margin: 0;
  color: var(--text-primary);
}

/* Footer */
.panel-footer {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 1rem 1.5rem;
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
  transition: opacity 0.2s ease;
}

.panel-enter-active .source-preview-panel,
.panel-leave-active .source-preview-panel {
  transition: transform 0.2s ease;
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
