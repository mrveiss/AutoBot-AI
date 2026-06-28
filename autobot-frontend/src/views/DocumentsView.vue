<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Issue #3245: Knowledge Base - persistent editable AI output documents -->
<template>
  <div class="documents-view">
    <div class="documents-sidebar">
      <div class="sidebar-header">
        <h2 class="sidebar-title">{{ $t('nav.documents') }}</h2>
        <BaseButton
          variant="primary"
          size="sm"
          :disabled="composable.isLoading.value"
          :title="$t('documents.refreshList')"
          @click="composable.fetchDocuments()"
        >
          <Icon name="sync-alt" aria-hidden="true" />
        </BaseButton>
      </div>

      <div v-if="composable.isLoading.value && !composable.hasDocuments.value" class="loading-state">
        <Icon name="sync-alt" :spin="true" aria-hidden="true" />
        <span>{{ $t('documents.loading') }}</span>
      </div>

      <div v-else-if="!composable.hasDocuments.value" class="empty-state">
        <Icon name="file-alt" class="empty-icon" aria-hidden="true" />
        <p>{{ $t('documents.noDocsYet') }}</p>
        <p class="empty-hint">
          {{ $t('documents.saveHintPrefix') }}
          <RouterLink to="/chat" class="chat-link">{{ $t('documents.chatViewLink') }}</RouterLink>
          {{ $t('documents.saveHintSuffix') }}
        </p>
      </div>

      <ul v-else class="document-list" role="listbox" :aria-label="$t('documents.listAriaLabel')">
        <li
          v-for="doc in composable.documents.value"
          :key="doc.id"
          class="document-item"
          :class="{ active: selectedDocId === doc.id }"
          role="option"
          :aria-selected="selectedDocId === doc.id"
          tabindex="0"
          @click="selectDocument(doc.id)"
          @keyup.enter="selectDocument(doc.id)"
        >
          <span class="doc-title">{{ doc.title }}</span>
          <span class="doc-meta">{{ formatDate(doc.updated_at) }}</span>
          <BaseButton
            variant="ghost"
            size="xs"
            class="delete-btn"
            :title="$t('documents.deleteDocument')"
            :aria-label="$t('documents.deleteAria', { title: doc.title })"
            @click.stop="confirmDelete(doc.id, doc.title)"
          >
            <Icon name="trash" aria-hidden="true" />
          </BaseButton>
        </li>
      </ul>

      <div v-if="composable.total.value > PAGE_SIZE" class="pagination">
        <BaseButton
          variant="ghost"
          size="sm"
          :disabled="currentOffset === 0"
          @click="prevPage"
        >
          {{ $t('documents.prev') }}
        </BaseButton>
        <span class="page-info">
          {{ $t('documents.pageRange', {
            start: currentOffset + 1,
            end: Math.min(currentOffset + PAGE_SIZE, composable.total.value),
            total: composable.total.value,
          }) }}
        </span>
        <BaseButton
          variant="ghost"
          size="sm"
          :disabled="currentOffset + PAGE_SIZE >= composable.total.value"
          @click="nextPage"
        >
          {{ $t('documents.next') }}
        </BaseButton>
      </div>
    </div>

    <div class="documents-main">
      <div v-if="!selectedDocId" class="no-selection">
        <!-- TASK 12: richer empty state when there are no documents at all -->
        <template v-if="!composable.hasDocuments.value">
          <Icon name="file-alt" class="no-selection-icon" aria-hidden="true" />
          <h3 class="no-selection-title">{{ $t('documents.emptyTitle') }}</h3>
          <p class="no-selection-sub">{{ $t('documents.emptySubtitle') }}</p>
          <RouterLink to="/chat" class="go-to-chat-btn">
            <Icon name="comments" aria-hidden="true" />
            <span>{{ $t('documents.goToChat') }}</span>
          </RouterLink>
        </template>
        <template v-else>
          <Icon name="file-alt" class="no-selection-icon" aria-hidden="true" />
          <p>{{ $t('documents.selectPrompt') }}</p>
        </template>
      </div>

      <AIDocumentEditor
        v-else
        :doc-id="selectedDocId"
        class="editor-panel"
        @saved="onDocumentSaved"
        @refined="onDocumentRefined"
        @error="onEditorError"
      />
    </div>

    <!-- Delete confirmation dialog -->
    <div
      v-if="deleteTarget"
      ref="deleteDialogRef"
      class="modal-overlay"
      role="dialog"
      aria-modal="true"
      :aria-label="$t('documents.confirmDeleteAria', { title: deleteTarget.title })"
      tabindex="-1"
      @keydown="onDeleteDialogKeydown"
      @keydown.escape="deleteTarget = null"
    >
      <div class="modal-card">
        <h3 class="modal-title">{{ $t('documents.deleteHeading') }}</h3>
        <p class="modal-body">
          {{ $t('documents.deleteBody', { title: deleteTarget.title }) }}
        </p>
        <div class="modal-actions">
          <BaseButton variant="ghost" size="sm" @click="deleteTarget = null">
            {{ $t('common.cancel') }}
          </BaseButton>
          <BaseButton
            variant="error"
            size="sm"
            :disabled="composable.isLoading.value"
            @click="executeDelete"
          >
            {{ $t('common.delete') }}
          </BaseButton>
        </div>
      </div>
    </div>

    <!-- Error toast -->
    <div v-if="errorMessage" class="error-toast" role="alert">
      {{ errorMessage }}
    </div>

    <!-- Transcriber Projects Section -->
    <section v-if="transcriberProjects.length" class="transcriber-section">
      <div class="section-header">
        <h3>{{ $t('documents.transcriberProjects') }}</h3>
        <RouterLink :to="{ name: 'transcriber-projects' }" class="btn-link">{{ $t('documents.viewAll') }}</RouterLink>
      </div>
      <div class="projects-mini-grid">
        <RouterLink
          v-for="p in transcriberProjects"
          :key="p.id"
          :to="{ name: 'transcriber-project-detail', params: { projectId: p.id } }"
          class="mini-card"
        >
          🎙 {{ p.name }}
        </RouterLink>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { RouterLink } from 'vue-router'
import BaseButton from '@/components/base/BaseButton.vue'
import AIDocumentEditor from '@/components/documents/AIDocumentEditor.vue'
import Icon from '@/components/ui/Icon.vue'
import { useAIDocument, type AIDocument } from '@/composables/useAIDocument'
import { useTranscriberApi } from '@/composables/transcriber/useTranscriberApi'
import type { Project } from '@/composables/transcriber/useTranscriberApi'
import { createLogger } from '@/utils/debugUtils'
import { useFocusTrap } from '@/composables/useFocusTrap'
import { useFocusRestore } from '@/composables/useFocusRestore'
import { useInitialFocus } from '@/composables/useInitialFocus'
import { useBodyScrollLock } from '@/composables/useBodyScrollLock'

const logger = createLogger('DocumentsView')
const transcriberApi = useTranscriberApi()
const transcriberProjects = ref<Project[]>([])

const PAGE_SIZE = 50

const composable = useAIDocument()
const selectedDocId = ref<string | null>(null)
const currentOffset = ref(0)
const deleteTarget = ref<{ id: string; title: string } | null>(null)

const deleteDialogRef = ref<HTMLElement | null>(null)
const isDeleteDialogOpen = computed(() => deleteTarget.value !== null)
const { onKeydown: onDeleteDialogKeydown } = useFocusTrap(deleteDialogRef)
useFocusRestore(isDeleteDialogOpen)
useBodyScrollLock(isDeleteDialogOpen)
const { focusFirst: focusDeleteFirst } = useInitialFocus(deleteDialogRef)
watch(isDeleteDialogOpen, (open) => { if (open) focusDeleteFirst() }, { immediate: true })
const errorMessage = ref<string | null>(null)

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onMounted(async () => {
  await loadPage()
  try {
    transcriberProjects.value = (await transcriberApi.listProjects()).slice(0, 4)
  } catch {
    /* transcriber may be disabled */
  }
})

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

async function loadPage() {
  try {
    await composable.fetchDocuments(PAGE_SIZE, currentOffset.value)
  } catch {
    showError(composable.error.value ?? 'Failed to load documents')
  }
}

function selectDocument(id: string) {
  selectedDocId.value = id
}

async function prevPage() {
  currentOffset.value = Math.max(0, currentOffset.value - PAGE_SIZE)
  await loadPage()
}

async function nextPage() {
  currentOffset.value += PAGE_SIZE
  await loadPage()
}

// ---------------------------------------------------------------------------
// Delete
// ---------------------------------------------------------------------------

function confirmDelete(id: string, title: string) {
  deleteTarget.value = { id, title }
}

async function executeDelete() {
  if (!deleteTarget.value) return
  const { id } = deleteTarget.value
  deleteTarget.value = null
  try {
    await composable.deleteDocument(id)
    if (selectedDocId.value === id) {
      selectedDocId.value = null
    }
    logger.info('Deleted document', id)
  } catch {
    showError(composable.error.value ?? 'Delete failed')
  }
}

// ---------------------------------------------------------------------------
// Editor callbacks
// ---------------------------------------------------------------------------

function onDocumentSaved(doc: AIDocument) {
  logger.info('Document saved', doc.id)
}

function onDocumentRefined(doc: AIDocument) {
  logger.info('Document refined', doc.id)
}

function onEditorError(message: string) {
  showError(message)
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return iso
  }
}

let errorTimer: ReturnType<typeof setTimeout> | null = null

function showError(msg: string) {
  errorMessage.value = msg
  if (errorTimer) clearTimeout(errorTimer)
  errorTimer = setTimeout(() => {
    errorMessage.value = null
  }, 5000)
}
</script>

<style scoped>
.documents-view {
  display: flex;
  height: 100%;
  background: var(--color-background, #1a1a1a);
  color: var(--color-text, #e0e0e0);
  position: relative;
  overflow: hidden;
}

/* Sidebar */
.documents-sidebar {
  width: 280px;
  min-width: 220px;
  max-width: 360px;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--color-border, #333);
  background: var(--color-background-secondary, #222);
  overflow: hidden;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-3-5) var(--spacing-4);
  border-bottom: 1px solid var(--color-border, #333);
  flex-shrink: 0;
}

.sidebar-title {
  margin: var(--spacing-0);
  font-size: var(--text-base);
  font-weight: 600;
}

/* States */
.loading-state,
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  padding: var(--spacing-6);
  text-align: center;
  color: var(--color-text-muted, #888);
  font-size: 0.9rem;
}

.empty-icon {
  font-size: 2rem;
  margin-bottom: var(--spacing-2);
  color: var(--color-text-muted, #555);
}

.empty-hint {
  font-size: 0.8rem;
  color: var(--color-text-muted, #666);
}

.chat-link {
  color: var(--color-primary, #4caf50);
  text-decoration: none;
}

.chat-link:hover {
  text-decoration: underline;
}

/* Document list */
.document-list {
  list-style: none;
  margin: var(--spacing-0);
  padding: var(--spacing-0);
  overflow-y: auto;
  flex: 1;
}

.document-item {
  display: flex;
  flex-direction: column;
  padding: var(--spacing-2-5) var(--spacing-4);
  cursor: pointer;
  border-bottom: 1px solid var(--color-border, #2a2a2a);
  gap: var(--spacing-0-5);
  position: relative;
  transition: background 0.12s;
}

.document-item:hover {
  background: var(--color-background-hover, #2a2a2a);
}

.document-item.active {
  background: var(--color-primary-dim, #1e3a1e);
  border-left: 3px solid var(--color-primary, #4caf50);
}

.doc-title {
  font-size: 0.9rem;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding-right: var(--spacing-7);
}

.doc-meta {
  font-size: 0.72rem;
  color: var(--color-text-muted, #888);
}

.delete-btn {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  opacity: 0;
  transition: opacity 0.12s;
}

.document-item:hover .delete-btn,
.document-item:focus .delete-btn {
  opacity: 1;
}

/* Pagination */
.pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-2) var(--spacing-3);
  border-top: 1px solid var(--color-border, #333);
  font-size: 0.8rem;
  flex-shrink: 0;
}

.page-info {
  color: var(--color-text-muted, #888);
}

/* Main panel */
.documents-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.no-selection {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-3);
  color: var(--color-text-muted, #888);
  font-size: 0.95rem;
}

.no-selection-icon {
  font-size: var(--text-5xl);
  color: var(--color-text-muted, #444);
}

/* TASK 12: rich empty state */
.no-selection-title {
  font-size: var(--text-xl, 1.25rem);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.no-selection-sub {
  max-width: 22rem;
  text-align: center;
  color: var(--text-secondary);
  margin: 0;
}

.go-to-chat-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  margin-top: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--color-primary);
  color: #fff;
  border-radius: var(--radius-md, 6px);
  font-size: 0.875rem;
  font-weight: 500;
  text-decoration: none;
  transition: background var(--duration-150) var(--ease-in-out);
}

.go-to-chat-btn:hover {
  background: var(--color-primary-hover, var(--color-primary));
}

.editor-panel {
  flex: 1;
  overflow: hidden;
}

/* Modal */
.modal-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.modal-card {
  background: var(--color-background-secondary, #252525);
  border: 1px solid var(--color-border, #444);
  border-radius: var(--radius-lg);
  padding: var(--spacing-6);
  width: 360px;
  max-width: 90vw;
}

.modal-title {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-3);
  font-size: var(--text-base);
  font-weight: 600;
}

.modal-body {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-5);
  font-size: 0.9rem;
  color: var(--color-text-muted, #bbb);
  line-height: 1.5;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-2);
}

/* Error toast */
.error-toast {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  background: var(--color-error-bg, #3c1515);
  color: var(--color-error, #f87171);
  border: 1px solid var(--color-error, #f87171);
  border-radius: var(--radius-md);
  padding: var(--spacing-2-5) var(--spacing-5);
  font-size: var(--text-sm);
  z-index: var(--z-popover);
  max-width: 90vw;
  text-align: center;
}
</style>
