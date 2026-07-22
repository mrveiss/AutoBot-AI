<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Issue #11526: Knowledge Browser – AI-documents branch component -->
<template>
  <details class="docs-branch" open>
    <summary class="branch-summary">
      <span>{{ $t('knowledge.documents') }}</span>
      <BaseButton
        variant="ghost"
        size="xs"
        class="refresh-btn"
        :disabled="composable.isLoading.value"
        :title="$t('documents.refreshList')"
        @click.stop="composable.fetchDocuments(PAGE_SIZE, currentOffset)"
      >
        <Icon name="sync-alt" aria-hidden="true" />
      </BaseButton>
    </summary>

    <!-- Loading state -->
    <div v-if="composable.isLoading.value && !composable.hasDocuments.value" class="loading-state">
      <Icon name="sync-alt" :spin="true" aria-hidden="true" />
      <span>{{ $t('documents.loading') }}</span>
    </div>

    <!-- Empty state -->
    <div v-else-if="!composable.hasDocuments.value" class="empty-state">
      <Icon name="file-alt" class="empty-icon" aria-hidden="true" />
      <p>{{ $t('documents.noDocsYet') }}</p>
      <p class="empty-hint">
        {{ $t('documents.saveHintPrefix') }}
        <RouterLink to="/chat" class="chat-link">{{ $t('documents.chatViewLink') }}</RouterLink>
        {{ $t('documents.saveHintSuffix') }}
      </p>
    </div>

    <!-- Document list -->
    <ul v-else class="document-list" role="listbox" :aria-label="$t('documents.listAriaLabel')">
      <li
        v-for="doc in composable.documents.value"
        :key="doc.id"
        class="document-item"
        :class="{ active: selectedDocId === doc.id }"
        role="option"
        :aria-selected="selectedDocId === doc.id"
        tabindex="0"
        @click="emit('select', doc.id)"
        @keyup.enter="emit('select', doc.id)"
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

    <!-- Pagination -->
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

    <!-- Transcriber Projects (nested branch, collapsed by default) -->
    <details v-if="transcriberProjects.length" class="transcriber-branch">
      <summary>{{ $t('documents.transcriberProjects') }}</summary>
      <div class="projects-mini-grid">
        <RouterLink
          v-for="p in transcriberProjects"
          :key="p.id"
          :to="{ name: 'transcriber-project-detail', params: { projectId: p.id } }"
          class="mini-card"
        >
          🎙 {{ p.name }}
        </RouterLink>
        <RouterLink :to="{ name: 'transcriber-projects' }" class="btn-link">
          {{ $t('documents.viewAll') }}
        </RouterLink>
      </div>
    </details>

    <!-- Delete confirmation dialog -->
    <BaseModal
      :model-value="!!deleteTarget"
      :title="$t('documents.deleteHeading')"
      :close-label="$t('ui.modal.closeDialog')"
      :width="360"
      @close="deleteTarget = null"
    >
      <p v-if="deleteTarget" class="modal-body">
        {{ $t('documents.deleteBody', { title: deleteTarget.title }) }}
      </p>

      <template #actions>
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
      </template>
    </BaseModal>
  </details>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import BaseButton from '@/components/base/BaseButton.vue'
import Icon from '@/components/ui/Icon.vue'
import { useAIDocument } from '@/composables/useAIDocument'
import { useTranscriberApi } from '@/composables/transcriber/useTranscriberApi'
import type { Project } from '@/composables/transcriber/useTranscriberApi'
import { createLogger } from '@/utils/debugUtils'
import { BaseModal } from '@autobot/ui'

const PAGE_SIZE = 50

const logger = createLogger('KnowledgeDocumentsBranch')

// ---------------------------------------------------------------------------
// Props / Emits
// ---------------------------------------------------------------------------

interface Props {
  selectedDocId: string | null
}

defineProps<Props>()

const emit = defineEmits<{
  select: [docId: string]
  deleted: [docId: string]
  error: [message: string]
}>()

// ---------------------------------------------------------------------------
// Composables
// ---------------------------------------------------------------------------

const composable = useAIDocument()
const transcriberApi = useTranscriberApi()
const transcriberProjects = ref<Project[]>([])

// ---------------------------------------------------------------------------
// Pagination state
// ---------------------------------------------------------------------------

const currentOffset = ref(0)

// ---------------------------------------------------------------------------
// Delete dialog
// ---------------------------------------------------------------------------

const deleteTarget = ref<{ id: string; title: string } | null>(null)

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
// Navigation / pagination
// ---------------------------------------------------------------------------

async function loadPage() {
  try {
    await composable.fetchDocuments(PAGE_SIZE, currentOffset.value)
  } catch {
    emit('error', composable.error.value ?? 'Failed to load documents')
  }
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
  try {
    await composable.deleteDocument(id)
    deleteTarget.value = null
    logger.info('Deleted document', id)
    emit('deleted', id)
  } catch {
    deleteTarget.value = null
    emit('error', composable.error.value ?? 'Delete failed')
  }
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
</script>

<style scoped>
.docs-branch {
  display: flex;
  flex-direction: column;
}

.branch-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-2) var(--spacing-3);
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  list-style: none;
  user-select: none;
}

.branch-summary::-webkit-details-marker {
  display: none;
}

.refresh-btn {
  flex-shrink: 0;
}

/* States */
.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  padding: var(--spacing-6);
  text-align: center;
  color: var(--text-muted);
  font-size: 0.9rem;
  flex: 1;
}

.empty-icon {
  font-size: 2rem;
  margin-bottom: var(--spacing-2);
  color: var(--text-muted);
}

.empty-hint {
  font-size: 0.8rem;
  color: var(--text-muted);
}

.chat-link {
  color: var(--color-primary);
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
  border-bottom: 1px solid var(--border-default);
  gap: var(--spacing-0-5);
  position: relative;
  transition: background 0.12s;
}

.document-item:hover {
  background: var(--bg-hover);
}

.document-item.active {
  background: var(--color-primary-bg);
  border-left: 3px solid var(--color-primary);
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
  color: var(--text-muted);
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
  border-top: 1px solid var(--border-default);
  font-size: 0.8rem;
  flex-shrink: 0;
}

.page-info {
  color: var(--text-muted);
}

/* Transcriber nested branch */
.transcriber-branch {
  border-top: 1px solid var(--border-default);
  font-size: var(--text-sm);
}

.transcriber-branch > summary {
  padding: var(--spacing-2) var(--spacing-3);
  cursor: pointer;
  font-weight: 500;
  color: var(--text-muted);
  list-style: none;
  user-select: none;
}

.transcriber-branch > summary::-webkit-details-marker {
  display: none;
}

.projects-mini-grid {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
  padding: var(--spacing-2) var(--spacing-3);
}

.mini-card {
  display: block;
  padding: var(--spacing-1-5) var(--spacing-2);
  border-radius: var(--radius-sm, 4px);
  font-size: 0.8rem;
  color: var(--text-primary);
  text-decoration: none;
  transition: background 0.12s;
}

.mini-card:hover {
  background: var(--bg-hover);
}

.btn-link {
  font-size: 0.75rem;
  color: var(--color-primary);
  text-decoration: none;
  padding: var(--spacing-1) var(--spacing-2);
}

.btn-link:hover {
  text-decoration: underline;
}

/* Modal */
/* #10882: overlay/header/footer chrome + focus-trap/scroll-lock now provided
   by @autobot/ui BaseModal; only the confirmation copy styling remains. */
.modal-body {
  margin: var(--spacing-0);
  font-size: 0.9rem;
  color: var(--text-muted);
  line-height: 1.5;
}
</style>
