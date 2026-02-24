<template>
  <Teleport to="body">
    <div v-if="visible" class="source-manager-overlay" @click.self="$emit('close')">
      <div class="source-manager-panel" role="dialog" aria-modal="true" aria-label="Code Source Manager">
        <!-- Panel Header -->
        <div class="panel-header">
          <div class="panel-title">
            <i class="fas fa-code-branch"></i>
            Code Source Registry
          </div>
          <div class="panel-header-actions">
            <span v-if="queueLength > 0" class="queue-badge">
              <i class="fas fa-clock"></i>
              {{ queueLength }} queued
            </span>
            <button class="btn-add" @click="$emit('open-add-source')">
              <i class="fas fa-plus"></i>
              Add Source
            </button>
            <button class="close-btn" @click="$emit('close')" aria-label="Close">
              <i class="fas fa-times"></i>
            </button>
          </div>
        </div>

        <!-- Loading State -->
        <div v-if="loading" class="panel-loading">
          <i class="fas fa-spinner fa-spin"></i>
          Loading sources...
        </div>

        <!-- Error State -->
        <div v-else-if="loadError" class="panel-error">
          <i class="fas fa-exclamation-triangle"></i>
          {{ loadError }}
          <button class="btn-retry" @click="loadSources">Retry</button>
        </div>

        <!-- Empty State -->
        <div v-else-if="sources.length === 0" class="panel-empty">
          <i class="fas fa-folder-open"></i>
          <p>No code sources registered.</p>
          <p class="panel-empty-hint">Add a GitHub repository or local path to get started.</p>
          <button class="btn-add" @click="$emit('open-add-source')">
            <i class="fas fa-plus"></i>
            Add Your First Source
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
                <i :class="source.source_type === 'github' ? 'fab fa-github' : 'fas fa-folder'"></i>
              </div>
              <div class="source-details">
                <div class="source-name">{{ source.name }}</div>
                <div class="source-meta">
                  <span v-if="source.repo" class="source-repo">{{ source.repo }}</span>
                  <span v-else-if="source.clone_path" class="source-path">{{ source.clone_path }}</span>
                  <span v-if="source.branch" class="source-branch">
                    <i class="fas fa-code-branch"></i> {{ source.branch }}
                  </span>
                </div>
                <div class="source-timestamps">
                  <span v-if="source.last_synced" class="source-synced">
                    Synced {{ formatRelativeTime(source.last_synced) }}
                  </span>
                  <span v-else class="source-never-synced">Never synced</span>
                </div>
              </div>
            </div>

            <!-- Badges -->
            <div class="source-badges">
              <span class="status-badge" :class="`status-badge--${source.status}`">
                <i :class="getStatusIcon(source.status)"></i>
                {{ source.status }}
              </span>
              <span class="access-badge" :class="`access-badge--${source.access}`">
                <i :class="getAccessIcon(source.access)"></i>
                {{ source.access }}
              </span>
            </div>

            <!-- Error Message -->
            <div v-if="source.status === 'error' && source.error_message" class="source-error">
              <i class="fas fa-exclamation-circle"></i>
              {{ source.error_message }}
            </div>

            <!-- Actions -->
            <div class="source-actions">
              <button
                class="btn-action btn-action--sync"
                :disabled="source.status === 'syncing' || syncingId === source.id"
                @click="syncSource(source)"
                :title="source.status === 'syncing' ? 'Syncing...' : 'Sync Now'"
              >
                <i :class="syncingId === source.id ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
              </button>
              <button
                class="btn-action btn-action--edit"
                @click="$emit('edit-source', source)"
                title="Edit"
              >
                <i class="fas fa-edit"></i>
              </button>
              <button
                class="btn-action btn-action--share"
                @click="$emit('share-source', source)"
                title="Share"
              >
                <i class="fas fa-share-alt"></i>
              </button>
              <button
                class="btn-action btn-action--delete"
                :disabled="deletingId === source.id"
                @click="deleteSource(source)"
                title="Delete"
              >
                <i :class="deletingId === source.id ? 'fas fa-spinner fa-spin' : 'fas fa-trash-alt'"></i>
              </button>
            </div>
          </div>
        </div>

        <!-- Queue Status Footer -->
        <div v-if="runningTask" class="queue-footer">
          <div class="queue-running">
            <i class="fas fa-spinner fa-spin"></i>
            <span>Indexing running</span>
            <span v-if="runningTask.source_id" class="queue-source-id">
              (source: {{ runningTask.source_id.substring(0, 8) }}...)
            </span>
            <button
              class="btn-dequeue"
              @click="cancelQueueItem(runningTask.source_id)"
              title="Remove from queue"
            >
              <i class="fas fa-ban"></i>
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

import { ref, watch, onUnmounted } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import appConfig from '@/config/AppConfig.js'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('SourceManager')

// ---- Types ----------------------------------------------------------------

interface CodeSource {
  id: string
  name: string
  source_type: 'github' | 'local'
  repo: string | null
  branch: string
  credential_id: string | null
  clone_path: string | null
  last_synced: string | null
  status: 'configured' | 'syncing' | 'ready' | 'error'
  error_message: string | null
  owner_id: string | null
  access: 'private' | 'shared' | 'public'
  shared_with: string[]
  created_at: string
}

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

// ---- State ----------------------------------------------------------------

const sources = ref<CodeSource[]>([])
const loading = ref(false)
const loadError = ref<string | null>(null)
const syncingId = ref<string | null>(null)
const deletingId = ref<string | null>(null)
const queueLength = ref(0)
const runningTask = ref<RunningTask | null>(null)
let syncingRefreshInterval: ReturnType<typeof setInterval> | null = null
let queuePollInterval: ReturnType<typeof setInterval> | null = null

// ---- API helpers ----------------------------------------------------------

async function getBackendUrl(): Promise<string> {
  return appConfig.getServiceUrl('backend')
}

// ---- Data Loading ---------------------------------------------------------

async function loadSources() {
  loading.value = true
  loadError.value = null
  try {
    const backendUrl = await getBackendUrl()
    const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/sources`)
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    const data = await response.json()
    sources.value = data.sources ?? []
    startSyncingRefreshIfNeeded()
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    logger.error('Failed to load sources:', msg)
    loadError.value = `Failed to load sources: ${msg}`
  } finally {
    loading.value = false
  }
}

async function loadQueueStatus() {
  try {
    const backendUrl = await getBackendUrl()
    const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/index/queue`)
    if (!response.ok) return
    const data = await response.json()
    queueLength.value = data.queue_length ?? 0
    runningTask.value = data.running ?? null
  } catch (err: unknown) {
    logger.warn('Failed to load queue status:', err instanceof Error ? err.message : String(err))
  }
}

// ---- Auto-refresh for syncing sources -------------------------------------

function startSyncingRefreshIfNeeded() {
  const hasSyncing = sources.value.some(s => s.status === 'syncing')
  if (hasSyncing && !syncingRefreshInterval) {
    syncingRefreshInterval = setInterval(async () => {
      await loadSources()
      if (!sources.value.some(s => s.status === 'syncing')) {
        stopSyncingRefresh()
      }
    }, 3000)
  }
}

function stopSyncingRefresh() {
  if (syncingRefreshInterval) {
    clearInterval(syncingRefreshInterval)
    syncingRefreshInterval = null
  }
}

// ---- Source Actions -------------------------------------------------------

async function syncSource(source: CodeSource) {
  syncingId.value = source.id
  try {
    const backendUrl = await getBackendUrl()
    const response = await fetchWithAuth(
      `${backendUrl}/api/analytics/codebase/sources/${source.id}/sync`,
      { method: 'POST' }
    )
    if (!response.ok) {
      const text = await response.text()
      throw new Error(`HTTP ${response.status}: ${text}`)
    }
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
  if (!confirm(`Delete source "${source.name}"? This cannot be undone.`)) return
  deletingId.value = source.id
  try {
    const backendUrl = await getBackendUrl()
    const response = await fetchWithAuth(
      `${backendUrl}/api/analytics/codebase/sources/${source.id}`,
      { method: 'DELETE' }
    )
    if (!response.ok) {
      const text = await response.text()
      throw new Error(`HTTP ${response.status}: ${text}`)
    }
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
    const backendUrl = await getBackendUrl()
    const response = await fetchWithAuth(
      `${backendUrl}/api/analytics/codebase/index/queue/${sourceId}`,
      { method: 'DELETE' }
    )
    if (!response.ok) {
      logger.warn('Could not cancel queue item')
      return
    }
    await loadQueueStatus()
  } catch (err: unknown) {
    logger.error('Cancel queue failed:', err instanceof Error ? err.message : String(err))
  }
}

// ---- Display Helpers ------------------------------------------------------

function getStatusIcon(status: string): string {
  const icons: Record<string, string> = {
    configured: 'fas fa-cog',
    syncing: 'fas fa-spinner fa-spin',
    ready: 'fas fa-check-circle',
    error: 'fas fa-exclamation-circle'
  }
  return icons[status] ?? 'fas fa-question-circle'
}

function getAccessIcon(access: string): string {
  const icons: Record<string, string> = {
    private: 'fas fa-lock',
    shared: 'fas fa-users',
    public: 'fas fa-globe'
  }
  return icons[access] ?? 'fas fa-lock'
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
    queuePollInterval = setInterval(loadQueueStatus, 5000)
  } else {
    if (queuePollInterval) {
      clearInterval(queuePollInterval)
      queuePollInterval = null
    }
    stopSyncingRefresh()
  }
}, { immediate: true })

onUnmounted(() => {
  if (queuePollInterval) clearInterval(queuePollInterval)
  stopSyncingRefresh()
})

// Expose for parent to call after saving
defineExpose({ loadSources })
</script>

<style scoped>
/* Issue #1133: Code Source Registry */

.source-manager-overlay {
  position: fixed;
  inset: 0;
  background: var(--bg-overlay-dark);
  z-index: 1000;
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
  margin: 0;
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
  gap: 0.2rem;
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
  gap: 0.25rem;
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
