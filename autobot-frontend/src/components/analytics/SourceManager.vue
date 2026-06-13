<template>
  <Teleport to="body">
    <div v-if="visible" class="source-manager-overlay" @click.self="$emit('close')">
      <div
        ref="dialogRef"
        class="source-manager-panel"
        role="dialog"
        aria-modal="true"
        :aria-label="$t('analytics.sources.registry')"
        tabindex="-1"
        @keydown="onFocusTrapKeydown"
        @keydown.escape="$emit('close')"
      >
        <!-- Panel Header -->
        <div class="panel-header">
          <div class="panel-title">
            <Icon name="code-branch" />
            {{ $t('analytics.sources.registry') }}
          </div>
          <div class="panel-header-actions">
            <span v-if="queueLength > 0" class="queue-badge">
              <Icon name="clock" />
              {{ queueLength }} {{ $t('analytics.sources.queued') }}
            </span>
            <button class="btn-add" @click="$emit('open-add-source')">
              <Icon name="plus" />
              {{ $t('analytics.sources.addSource') }}
            </button>
            <button class="close-btn" @click="$emit('close')" :aria-label="$t('common.close')">
              <Icon name="times" />
            </button>
          </div>
        </div>

        <!-- Loading State -->
        <div v-if="loading" class="panel-loading">
          <Icon name="spinner" class="animate-spin" />
          {{ $t('analytics.sources.loading') }}
        </div>

        <!-- Error State -->
        <div v-else-if="loadError" class="panel-error">
          <Icon name="exclamation-triangle" />
          {{ loadError }}
          <button class="btn-retry" @click="loadSources">{{ $t('analytics.sources.retry') }}</button>
        </div>

        <!-- Empty State -->
        <div v-else-if="sources.length === 0" class="panel-empty">
          <Icon name="folder-open" />
          <p>{{ $t('analytics.sources.noSources') }}</p>
          <p class="panel-empty-hint">{{ $t('analytics.sources.noSourcesHint') }}</p>
          <button class="btn-add" @click="$emit('open-add-source')">
            <Icon name="plus" />
            {{ $t('analytics.sources.addFirstSource') }}
          </button>
        </div>

        <!-- Sources List -->
        <div v-else class="sources-list">
          <div
            v-for="source in sources"
            :key="source.id"
            class="source-item"
            :class="{
              'source-item--selected': source.id === selectedSourceId,
              'source-item--syncing': source.status === 'syncing',
              'source-item--error': source.status === 'error'
            }"
          >
            <!-- Source Info -->
            <div class="source-info" @click="$emit('select-source', source)" role="button" tabindex="0"
              @keydown.enter="$emit('select-source', source)">
              <div class="source-icon">
                <i :class="source.source_type === 'github' ? 'github' : 'folder'"></i>
              </div>
              <div class="source-details">
                <div class="source-name">{{ source.name }}</div>
                <div class="source-meta">
                  <span v-if="source.repo" class="source-repo">{{ source.repo }}</span>
                  <span v-else-if="source.clone_path" class="source-path">{{ source.clone_path }}</span>
                  <span v-if="source.branch" class="source-branch">
                    <Icon name="code-branch" /> {{ source.branch }}
                  </span>
                </div>
                <div class="source-timestamps">
                  <span v-if="source.last_synced" class="source-synced">
                    {{ $t('analytics.sources.synced') }} {{ formatRelativeTime(source.last_synced) }}
                  </span>
                  <span v-else class="source-never-synced">{{ $t('analytics.sources.neverSynced') }}</span>
                </div>
              </div>
            </div>

            <!-- Badges -->
            <div class="source-badges">
              <span class="status-badge" :class="`status-badge--${source.status}`">
                <Icon :name="getStatusIcon(source.status)" />
                {{ source.status }}
              </span>
              <span class="access-badge" :class="`access-badge--${source.access}`">
                <Icon :name="getAccessIcon(source.access)" />
                {{ source.access }}
              </span>
            </div>

            <!-- Error Message -->
            <div v-if="source.status === 'error' && source.error_message" class="source-error">
              <Icon name="exclamation-circle" />
              {{ source.error_message }}
            </div>

            <!-- Actions -->
            <div class="source-actions">
              <button
                class="btn-action btn-action--sync"
                :disabled="source.status === 'syncing' || syncingId === source.id"
                @click="syncSource(source)"
                :title="source.status === 'syncing' ? $t('analytics.sources.syncing') : $t('analytics.sources.syncNow')"
              >
                <i :class="syncingId === source.id ? 'fas fa-spinner fa-spin' : 'sync-alt'"></i>
              </button>
              <button
                class="btn-action btn-action--edit"
                @click="$emit('edit-source', source)"
                :title="$t('analytics.sources.edit')"
              >
                <Icon name="edit" />
              </button>
              <button
                class="btn-action btn-action--share"
                @click="$emit('share-source', source)"
                :title="$t('common.share')"
              >
                <Icon name="share-alt" />
              </button>
              <button
                class="btn-action btn-action--delete"
                :disabled="deletingId === source.id"
                @click="deleteSource(source)"
                :title="$t('analytics.sources.deleteTitle')"
              >
                <i :class="deletingId === source.id ? 'fas fa-spinner fa-spin' : 'trash-alt'"></i>
              </button>
            </div>
          </div>
        </div>

        <!-- Queue Status Footer -->
        <div v-if="runningTask" class="queue-footer">
          <div class="queue-running">
            <Icon name="spinner" class="animate-spin" />
            <span>{{ $t('analytics.sources.indexingRunning') }}</span>
            <span v-if="runningTask.source_id" class="queue-source-id">
              (source: {{ runningTask.source_id.substring(0, 8) }}...)
            </span>
            <button
              class="btn-dequeue"
              @click="cancelQueueItem(runningTask.source_id)"
              :title="$t('analytics.sources.removeFromQueue')"
            >
              <Icon name="ban" />
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * SourceManager Panel Component
 *
 * Displays registered code sources with CRUD, sync, and queue status.
 * Issue #1133: Code Source Registry for codebase analytics.
 */

import type { IconName } from '@/components/ui/Icon.vue'
import Icon from '@/components/ui/Icon.vue'
import { ref, watch, toRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { useFocusTrap } from '@/composables/useFocusTrap'
import { useFocusRestore } from '@/composables/useFocusRestore'
import { useInitialFocus } from '@/composables/useInitialFocus'
import { useBodyScrollLock } from '@/composables/useBodyScrollLock'
import { usePollingJob } from '@/composables/usePollingJob'
import { useAnalyticsSourceManagement } from '@/composables/analytics/useAnalyticsSourceManagement'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('SourceManager')
const { t } = useI18n()

// ---- Types ----------------------------------------------------------------

import type { CodeSource } from '@/types/analytics'

interface RunningTask {
  task_id: string
  source_id?: string
  started_at?: string
}

// ---- Props & Emits --------------------------------------------------------

interface Props {
  selectedSourceId: string | null
  visible: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'select-source', source: CodeSource): void
  (e: 'open-add-source'): void
  (e: 'edit-source', source: CodeSource): void
  (e: 'share-source', source: CodeSource): void
  (e: 'close'): void
}>()

const dialogRef = ref<HTMLElement | null>(null)
const { onKeydown: onFocusTrapKeydown } = useFocusTrap(dialogRef)
useFocusRestore(toRef(props, 'visible'))
useBodyScrollLock(toRef(props, 'visible'))
const { focusFirst } = useInitialFocus(dialogRef)
watch(() => props.visible, (open) => { if (open) focusFirst() }, { immediate: true })

// ---- Composable -----------------------------------------------------------

const {
  isLoadingSources,
  sourcesError,
  fetchSources,
  fetchQueueStatus,
  fetchSourcesForPolling,
  fetchQueueStatusForPolling,
  syncSource: apiSyncSource,
  deleteSource: apiDeleteSource,
  cancelQueueItem: apiCancelQueueItem,
} = useAnalyticsSourceManagement()

// ---- State ----------------------------------------------------------------

const sources = ref<CodeSource[]>([])
const loading = isLoadingSources
const loadError = sourcesError
const syncingId = ref<string | null>(null)
const deletingId = ref<string | null>(null)
const queueLength = ref(0)
const runningTask = ref<RunningTask | null>(null)

// Queue status polling (visible while panel is open, 5s interval)
const queuePoller = usePollingJob<{ queue_length: number; running: RunningTask | null }>(
  async (_taskId) => fetchQueueStatusForPolling(),
  {
    intervalMs: 5000,
    onDone: (data) => {
      queueLength.value = data.queue_length ?? 0
      runningTask.value = data.running ?? null
    },
  }
)

// Syncing-source refresh polling (3s interval, stops when no sources are syncing)
const syncingPoller = usePollingJob<CodeSource[]>(
  async (_taskId) => fetchSourcesForPolling(),
  {
    intervalMs: 3000,
    isComplete: (srcs) => !srcs.some((s) => s.status === 'syncing'),
    onDone: (srcs) => { sources.value = srcs },
  }
)

// ---- Data Loading ---------------------------------------------------------

async function loadSources() {
  try {
    sources.value = await fetchSources()
    startSyncingRefreshIfNeeded()
  } catch {
    // error already stored in loadError (sourcesError) by the composable
  }
}

async function loadQueueStatus() {
  const data = await fetchQueueStatus()
  if (data) {
    queueLength.value = data.queue_length
    runningTask.value = data.running
  }
}

// Queue poller data watcher — keep refs in sync while polling is active
watch(queuePoller.data, (data: { queue_length: number; running: RunningTask | null } | null) => {
  if (data) {
    queueLength.value = data.queue_length ?? 0
    runningTask.value = data.running ?? null
  }
})

// ---- Auto-refresh for syncing sources -------------------------------------

function startSyncingRefreshIfNeeded() {
  if (sources.value.some((s: CodeSource) => s.status === 'syncing') && !syncingPoller.isPolling.value) {
    syncingPoller.start('')
  }
}

// Syncing poller data watcher — keep sources in sync while polling is active
watch(syncingPoller.data, (srcs: CodeSource[] | null) => {
  if (srcs) sources.value = srcs
})

// ---- Source Actions -------------------------------------------------------

async function syncSource(source: CodeSource) {
  syncingId.value = source.id
  try {
    await apiSyncSource(source.id)
    logger.info('Sync started for source:', source.name)
    await loadSources()
    await loadQueueStatus()
  } catch (err: unknown) {
    logger.error('Sync failed:', err instanceof Error ? err.message : String(err))
  } finally {
    syncingId.value = null
  }
}

async function deleteSource(source: CodeSource) {
  if (!confirm(t('analytics.sources.confirmDelete', { name: source.name }))) return
  deletingId.value = source.id
  try {
    await apiDeleteSource(source.id)
    logger.info('Deleted source:', source.name)
    await loadSources()
  } catch (err: unknown) {
    logger.error('Delete failed:', err instanceof Error ? err.message : String(err))
  } finally {
    deletingId.value = null
  }
}

async function cancelQueueItem(sourceId: string | undefined) {
  if (!sourceId) return
  try {
    await apiCancelQueueItem(sourceId)
    await loadQueueStatus()
  } catch (err: unknown) {
    logger.error('Cancel queue failed:', err instanceof Error ? err.message : String(err))
  }
}

// ---- Display Helpers ------------------------------------------------------

function getStatusIcon(status: string): IconName {
  const icons: Record<string, IconName> = {
    configured: 'cog',
    // #9724: was an FA class string, which <Icon> rendered as an empty SVG
    syncing: 'spinner',
    ready: 'check-circle',
    error: 'exclamation-circle'
  }
  return icons[status] ?? 'question-circle'
}

function getAccessIcon(access: string): IconName {
  const icons: Record<string, IconName> = {
    private: 'lock',
    shared: 'users',
    public: 'globe'
  }
  return icons[access] ?? 'lock'
}

function formatRelativeTime(isoString: string): string {
  const now = Date.now()
  const then = new Date(isoString).getTime()
  const diffMs = now - then
  const diffMins = Math.floor(diffMs / 60000)
  if (diffMins < 1) return 'just now'
  if (diffMins < 60) return `${diffMins}m ago`
  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  return `${Math.floor(diffHours / 24)}d ago`
}

// ---- Lifecycle ------------------------------------------------------------

watch(() => props.visible, (visible) => {
  if (visible) {
    loadSources()
    loadQueueStatus()
    queuePoller.start('')
  } else {
    queuePoller.stop()
    syncingPoller.stop()
  }
}, { immediate: true })

// Expose for parent to call after saving
defineExpose({ loadSources })
</script>

<style scoped>
/* Issue #1133: Code Source Registry */

.source-manager-overlay {
  position: fixed;
  inset: 0;
  background: var(--bg-overlay-dark);
  z-index: var(--z-modal);
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  padding: var(--spacing-4);
}

.source-manager-panel {
  background: var(--bg-primary);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-2xl);
  width: 100%;
  max-width: 640px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Header */
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-5) var(--spacing-6);
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
  flex-shrink: 0;
}

.panel-title {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.panel-title i {
  color: var(--color-info);
}

.panel-header-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.queue-badge {
  background: var(--color-warning);
  color: var(--bg-secondary);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  padding: var(--spacing-1) var(--spacing-2-5);
  border-radius: var(--radius-full);
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
}

.btn-add {
  background: var(--color-info);
  color: var(--bg-secondary);
  border: none;
  border-radius: var(--radius-lg);
  padding: var(--spacing-2) var(--spacing-4);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  transition: background var(--duration-200);
}

.btn-add:hover {
  background: var(--color-info-dark);
}

.close-btn {
  width: 2rem;
  height: 2rem;
  border: none;
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--duration-200);
}

.close-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

/* States */
.panel-loading,
.panel-error,
.panel-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-3);
  padding: var(--spacing-12);
  color: var(--text-muted);
  font-size: var(--text-sm);
  text-align: center;
  flex: 1;
}

.panel-loading i,
.panel-error i,
.panel-empty > i {
  font-size: 2.5rem;
  margin-bottom: var(--spacing-2);
}

.panel-error {
  color: var(--color-error);
}

.panel-empty > i {
  color: var(--text-muted);
}

.panel-empty p {
  margin: var(--spacing-0);
}

.panel-empty-hint {
  color: var(--text-muted);
  font-size: var(--text-xs);
}

.btn-retry {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  padding: var(--spacing-1-5) var(--spacing-3);
  cursor: pointer;
  font-size: var(--text-sm);
}

/* Sources List */
.sources-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-3);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.source-item {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
  transition: border-color var(--duration-200), box-shadow var(--duration-200);
}

.source-item:hover {
  border-color: var(--border-default);
  box-shadow: var(--shadow-sm);
}

.source-item--selected {
  border-color: var(--color-info);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
}

.source-item--error {
  border-color: var(--color-error);
}

.source-item--syncing {
  border-color: var(--color-warning);
}

/* Source Info Row */
.source-info {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-3);
  cursor: pointer;
  flex: 1;
}

.source-icon {
  width: 2.5rem;
  height: 2.5rem;
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--color-info);
  font-size: var(--text-lg);
}

.source-details {
  flex: 1;
  min-width: 0;
}

.source-name {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  font-size: var(--text-sm);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.source-meta {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin-top: var(--spacing-1);
  flex-wrap: wrap;
}

.source-repo,
.source-path {
  color: var(--text-secondary);
  font-size: var(--text-xs);
  font-family: var(--font-mono, monospace);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 240px;
}

.source-branch {
  color: var(--text-muted);
  font-size: var(--text-xs);
  display: flex;
  align-items: center;
  gap: var(--spacing-micro-3);
}

.source-timestamps {
  margin-top: var(--spacing-1);
}

.source-synced,
.source-never-synced {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

/* Badges Row */
.source-badges {
  display: flex;
  gap: var(--spacing-2);
  flex-wrap: wrap;
}

.status-badge,
.access-badge {
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  padding: 0.15rem var(--spacing-2);
  border-radius: var(--radius-full);
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
  text-transform: capitalize;
}

.status-badge--configured {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.status-badge--syncing {
  background: rgba(245, 158, 11, 0.15);
  color: var(--color-warning);
}

.status-badge--ready {
  background: rgba(16, 185, 129, 0.15);
  color: var(--color-success);
}

.status-badge--error {
  background: rgba(239, 68, 68, 0.15);
  color: var(--color-error);
}

.access-badge--private {
  background: var(--bg-tertiary);
  color: var(--text-muted);
}

.access-badge--shared {
  background: rgba(59, 130, 246, 0.12);
  color: var(--color-info);
}

.access-badge--public {
  background: rgba(16, 185, 129, 0.12);
  color: var(--color-success);
}

/* Error message */
.source-error {
  font-size: var(--text-xs);
  color: var(--color-error);
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-1-5);
  background: rgba(239, 68, 68, 0.08);
  padding: var(--spacing-2) var(--spacing-3);
  border-radius: var(--radius-md);
}

/* Actions Row */
.source-actions {
  display: flex;
  gap: var(--spacing-1-5);
  justify-content: flex-end;
}

.btn-action {
  width: 1.75rem;
  height: 1.75rem;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xs);
  transition: all var(--duration-200);
}

.btn-action:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-action--sync {
  background: rgba(59, 130, 246, 0.15);
  color: var(--color-info);
}

.btn-action--sync:hover:not(:disabled) {
  background: rgba(59, 130, 246, 0.3);
}

.btn-action--edit {
  background: rgba(245, 158, 11, 0.15);
  color: var(--color-warning);
}

.btn-action--edit:hover {
  background: rgba(245, 158, 11, 0.3);
}

.btn-action--share {
  background: rgba(16, 185, 129, 0.15);
  color: var(--color-success);
}

.btn-action--share:hover {
  background: rgba(16, 185, 129, 0.3);
}

.btn-action--delete {
  background: rgba(239, 68, 68, 0.15);
  color: var(--color-error);
}

.btn-action--delete:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.3);
}

/* Queue Footer */
.queue-footer {
  padding: var(--spacing-3) var(--spacing-5);
  border-top: 1px solid var(--border-default);
  background: var(--bg-secondary);
  flex-shrink: 0;
}

.queue-running {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-xs);
  color: var(--color-warning);
}

.queue-source-id {
  color: var(--text-muted);
  font-family: var(--font-mono, monospace);
}

.btn-dequeue {
  margin-left: auto;
  background: rgba(239, 68, 68, 0.15);
  color: var(--color-error);
  border: none;
  border-radius: var(--radius-md);
  padding: var(--spacing-1) var(--spacing-2);
  cursor: pointer;
  font-size: var(--text-xs);
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
}

.btn-dequeue:hover {
  background: rgba(239, 68, 68, 0.3);
}
</style>
