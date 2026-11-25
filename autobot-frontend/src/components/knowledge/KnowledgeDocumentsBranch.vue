<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Issue #11526: Knowledge Browser – AI-documents branch component -->
<template>
  <details class="docs-branch" open>
    <summary class="branch-summary">
      <span class="branch-title">{{ $t('knowledge.documents') }}</span>
      <BaseTooltip :text="$t('documents.refreshList')" placement="left">
        <template #default="{ describedby }">
          <BaseButton
            variant="ghost"
            size="xs"
            class="refresh-btn"
            :disabled="composable.isLoading.value"
            :aria-label="$t('documents.refreshList')"
            :aria-describedby="describedby"
            @click.stop.prevent="composable.fetchDocuments(PAGE_SIZE, currentOffset)"
          >
            <Icon name="sync-alt" aria-hidden="true" />
          </BaseButton>
        </template>
      </BaseTooltip>
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
        <Icon name="file-alt" class="doc-icon" aria-hidden="true" />
        <BaseTooltip :text="doc.title" placement="top" class="doc-text">
          <template #default="{ describedby }">
            <span class="doc-title-wrap" :aria-describedby="describedby">
              <b class="doc-title">{{ doc.title }}</b>
              <span class="doc-meta">{{ formatDate(doc.updated_at) }}</span>
            </span>
          </template>
        </BaseTooltip>
        <BaseTooltip :text="$t('documents.deleteDocument')" placement="left">
          <template #default="{ describedby }">
            <BaseButton
              variant="ghost"
              size="xs"
              class="delete-btn"
              :aria-label="$t('documents.deleteAria', { title: doc.title })"
              :aria-describedby="describedby"
              @click.stop="confirmDelete(doc.id, doc.title)"
            >
              <Icon name="trash" aria-hidden="true" />
            </BaseButton>
          </template>
        </BaseTooltip>
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
          <Icon name="microphone" aria-hidden="true" /> {{ p.name }}
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
import Icon from '@/components/ui/Icon.vue'
import { useAIDocument } from '@/composables/useAIDocument'
import { useTranscriberApi } from '@/composables/transcriber/useTranscriberApi'
import type { Project } from '@/composables/transcriber/useTranscriberApi'
import { createLogger } from '@/utils/debugUtils'
import { BaseModal, BaseButton, BaseTooltip } from '@autobot/ui'
import { useI18n } from 'vue-i18n'
import { createDateFormatter } from '@/utils/formatHelpers'

const PAGE_SIZE = 50
const { t } = useI18n()

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
    emit('error', composable.error.value ?? t('documents.loadFailed'))
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
    emit('error', composable.error.value ?? t('documents.deleteFailed'))
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const formatDate = createDateFormatter({ kind: 'date', intl: { year: 'numeric', month: 'short', day: 'numeric' } })
</script>

<style scoped>
.docs-branch {
  border-block-start: var(--bw) solid var(--line);
  padding-block-start: var(--spacing-2);
}

.branch-summary {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-1) var(--spacing-2);
  cursor: pointer;
  list-style: none;
}

.branch-summary::-webkit-details-marker {
  display: none;
}

.branch-title {
  flex: 1;
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text);
}

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-4);
  font-size: var(--text-sm);
  color: var(--muted);
  text-align: center;
}

.empty-state p {
  margin: 0;
}

.chat-link {
  color: var(--link);
  text-decoration: underline;
}

.document-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: var(--spacing-2);
  list-style: none;
}

.document-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2);
  border-radius: var(--radius-md);
  border-inline-start: 3px solid transparent;
  cursor: pointer;
}

.document-item:hover,
.document-item.active {
  background: var(--surface2);
}

.document-item.active {
  border-inline-start-color: var(--primary);
}

.document-item:focus-visible {
  outline: 3px solid var(--focus);
  outline-offset: 2px;
}

.doc-icon {
  flex: none;
  color: var(--stroke);
}

.doc-text {
  flex: 1;
  min-inline-size: 0;
}

.doc-title-wrap {
  display: flex;
  flex-direction: column;
  min-inline-size: 0;
}

.doc-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text);
}

.doc-meta {
  font-size: var(--text-xs);
  color: var(--muted);
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-2);
}

.page-info {
  font-size: var(--text-xs);
  color: var(--muted);
}

.transcriber-branch {
  padding: var(--spacing-2);
  font-size: var(--text-sm);
}

.projects-mini-grid {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
  padding-block-start: var(--spacing-2);
}

.mini-card,
.btn-link {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-md);
  border: var(--bw) solid var(--border);
  color: var(--text);
  text-decoration: none;
}

.mini-card:hover,
.btn-link:hover {
  background: var(--surface2);
}

.modal-body {
  margin: 0;
  color: var(--text);
}
</style>
