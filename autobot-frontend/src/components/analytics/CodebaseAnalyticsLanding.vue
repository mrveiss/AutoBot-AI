<template>
  <div class="analytics-landing">
    <!-- Header -->
    <div class="landing-header">
      <div class="landing-header-text">
        <h1 class="landing-title">
          <i class="fas fa-chart-bar"></i>
          {{ $t('analytics.codebase.title') }}
        </h1>
        <p class="landing-subtitle">{{ $t('analytics.codebase.landing.subtitle') }}</p>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="landing-loading">
      <i class="fas fa-spinner fa-spin"></i>
      {{ $t('analytics.sources.loading') }}
    </div>

    <!-- Projects Grid -->
    <div v-else class="projects-grid">
      <div
        v-for="source in sources"
        :key="source.id"
        class="project-card"
        :class="{
          'project-card--syncing': source.status === 'syncing',
          'project-card--error': source.status === 'error'
        }"
        role="button"
        tabindex="0"
        @click="openProject(source.id)"
        @keydown.enter="openProject(source.id)"
      >
        <!-- Card Header -->
        <div class="card-header">
          <div class="card-icon">
            <i :class="source.source_type === 'github' ? 'fab fa-github' : 'fas fa-folder'"></i>
          </div>
          <div class="card-badges">
            <span class="status-badge" :class="`status-badge--${source.status}`">
              <i :class="getStatusIcon(source.status)"></i>
              {{ source.status }}
            </span>
            <span class="access-badge" :class="`access-badge--${source.access}`">
              <i :class="getAccessIcon(source.access)"></i>
              {{ source.access }}
            </span>
          </div>
        </div>

        <!-- Card Body -->
        <div class="card-body">
          <div class="card-name">{{ source.name }}</div>
          <div class="card-meta">
            <span v-if="source.repo" class="card-repo">
              <i class="fas fa-link"></i> {{ source.repo }}
            </span>
            <span v-else-if="source.clone_path" class="card-repo">
              <i class="fas fa-folder-open"></i> {{ source.clone_path }}
            </span>
            <span v-if="source.branch" class="card-branch">
              <i class="fas fa-code-branch"></i> {{ source.branch }}
            </span>
          </div>
        </div>

        <!-- Error Message -->
        <div v-if="source.status === 'error' && source.error_message" class="card-error">
          <i class="fas fa-exclamation-circle"></i>
          {{ source.error_message }}
        </div>

        <!-- Actions (#1468) -->
        <div class="card-actions" @click.stop>
          <button
            class="btn-card-action btn-card-action--sync"
            :disabled="source.status === 'syncing' || syncingId === source.id"
            :title="source.status === 'syncing' ? $t('analytics.sources.syncing') : $t('analytics.sources.syncNow')"
            @click="syncSource(source)"
          >
            <i :class="syncingId === source.id ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
          </button>
          <button
            class="btn-card-action btn-card-action--delete"
            :disabled="deletingId === source.id"
            :title="$t('analytics.sources.deleteTitle')"
            @click="deleteSource(source)"
          >
            <i :class="deletingId === source.id ? 'fas fa-spinner fa-spin' : 'fas fa-trash-alt'"></i>
          </button>
        </div>

        <!-- Timestamps -->
        <div class="card-timestamps">
          <div class="timestamp-row">
            <i class="fas fa-sync-alt"></i>
            <span v-if="source.last_synced" class="timestamp-text">
              {{ $t('analytics.sources.synced') }} {{ formatRelativeTime(source.last_synced) }}
            </span>
            <span v-else class="timestamp-text timestamp-text--muted">
              {{ $t('analytics.sources.neverSynced') }}
            </span>
          </div>
          <div class="timestamp-row">
            <i class="fas fa-database"></i>
            <span
              v-if="summaries[source.id]?.last_indexed"
              class="timestamp-text"
            >
              {{ $t('analytics.codebase.landing.indexed') }}
              {{ formatRelativeTime(summaries[source.id].last_indexed!) }}
            </span>
            <span v-else class="timestamp-text timestamp-text--muted">
              {{ $t('analytics.codebase.landing.neverIndexed') }}
            </span>
          </div>
          <div v-if="summaries[source.id]?.last_commit" class="timestamp-row">
            <i class="fas fa-code-commit"></i>
            <span class="timestamp-text">
              {{ formatRelativeTime(summaries[source.id].last_commit!.timestamp) }}
            </span>
            <a
              v-if="summaries[source.id].last_commit!.url"
              :href="summaries[source.id].last_commit!.url!"
              class="commit-link"
              target="_blank"
              rel="noopener noreferrer"
              @click.stop
            >
              {{ summaries[source.id].last_commit!.short_hash }}
            </a>
            <span v-else class="commit-hash">
              {{ summaries[source.id].last_commit!.short_hash }}
            </span>
          </div>
        </div>
      </div>

      <!-- Add Project Card -->
      <div
        class="project-card project-card--add"
        role="button"
        tabindex="0"
        @click="showAddModal = true"
        @keydown.enter="showAddModal = true"
      >
        <i class="fas fa-plus"></i>
        <span>{{ $t('analytics.codebase.landing.addProject') }}</span>
      </div>
    </div>

    <!-- Add Source Modal -->
    <AddSourceModal
      :visible="showAddModal"
      @close="showAddModal = false"
      @saved="handleSourceSaved"
    />
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * CodebaseAnalyticsLanding — Project Cards Landing Page
 *
 * Shows a grid of registered code sources. Click a card to navigate
 * to the per-project analytics view.
 * Issue #1458
 */

import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import appConfig from '@/config/AppConfig.js'
import { createLogger } from '@/utils/debugUtils'
import AddSourceModal from '@/components/analytics/AddSourceModal.vue'

const logger = createLogger('CodebaseAnalyticsLanding')
const router = useRouter()
const { t } = useI18n()

// ---- Types ----------------------------------------------------------------

interface CodeSource {
  id: string
  name: string
  source_type: 'github' | 'local'
  repo: string | null
  branch: string
  clone_path: string | null
  last_synced: string | null
  status: 'configured' | 'syncing' | 'ready' | 'error'
  error_message: string | null
  access: 'private' | 'shared' | 'public'
}

interface SourceSummary {
  last_indexed: string | null
  last_commit: {
    hash: string
    short_hash: string
    message: string
    timestamp: string
    url: string | null
  } | null
}

// ---- State ----------------------------------------------------------------

const sources = ref<CodeSource[]>([])
const summaries = ref<Record<string, SourceSummary>>({})
const loading = ref(false)
const showAddModal = ref(false)
const syncingId = ref<string | null>(null)
const deletingId = ref<string | null>(null)

// ---- API helpers ----------------------------------------------------------

async function getBackendUrl(): Promise<string> {
  return appConfig.getServiceUrl('backend')
}

// ---- Data Loading ---------------------------------------------------------

async function loadSources() {
  loading.value = true
  try {
    const backendUrl = await getBackendUrl()
    const response = await fetchWithAuth(
      `${backendUrl}/api/analytics/codebase/sources`
    )
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    const data = await response.json()
    sources.value = data.sources ?? []

    await loadSummaries()
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    logger.error('Failed to load sources:', msg)
  } finally {
    loading.value = false
  }
}

async function loadSummaries() {
  const backendUrl = await getBackendUrl()
  try {
    const resp = await fetchWithAuth(
      `${backendUrl}/api/analytics/codebase/sources/summary`
    )
    if (!resp.ok) {
      logger.warn('Batch summary failed, HTTP %d', resp.status)
      return
    }
    const data = await resp.json()
    summaries.value = data.summaries ?? {}
  } catch (err: unknown) {
    logger.error(
      'Failed to load summaries:',
      err instanceof Error ? err.message : String(err)
    )
  }
}

// ---- Navigation -----------------------------------------------------------

function openProject(sourceId: string) {
  router.push({ name: 'analytics-codebase-project', params: { sourceId } })
}

// ---- Display Helpers ------------------------------------------------------

function formatRelativeTime(isoString: string): string {
  const now = Date.now()
  const then = new Date(isoString).getTime()
  const diffMs = now - then
  const diffMins = Math.floor(diffMs / 60000)
  if (diffMins < 1) return t('common.justNow', 'just now')
  if (diffMins < 60) return t('common.timeAgo.minutes', { n: diffMins })
  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return t('common.timeAgo.hours', { n: diffHours })
  return t('common.timeAgo.days', { n: Math.floor(diffHours / 24) })
}

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

// ---- Source Actions (#1468) ------------------------------------------------

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
  } catch (err: unknown) {
    logger.error(
      'Sync failed:',
      err instanceof Error ? err.message : String(err)
    )
  } finally {
    syncingId.value = null
  }
}

async function deleteSource(source: CodeSource) {
  const msg = t(
    'analytics.sources.confirmDelete', { name: source.name }
  )
  if (!confirm(msg)) return
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
    logger.error(
      'Delete failed:',
      err instanceof Error ? err.message : String(err)
    )
  } finally {
    deletingId.value = null
  }
}

// ---- Modal Handlers -------------------------------------------------------

function handleSourceSaved() {
  showAddModal.value = false
  loadSources()
}

// ---- Lifecycle ------------------------------------------------------------

onMounted(() => {
  loadSources()
})
</script>

<style scoped>
/* Issue #1458: Codebase Analytics Landing Page */

.analytics-landing {
  padding: var(--spacing-6) var(--spacing-8);
  max-width: 1400px;
  margin: 0 auto;
}

/* Header */
.landing-header {
  margin-bottom: var(--spacing-8);
}

.landing-title {
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
  margin: 0 0 var(--spacing-2) 0;
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
}

.landing-title i {
  color: var(--color-info);
}

.landing-subtitle {
  font-size: var(--text-sm);
  color: var(--text-muted);
  margin: 0;
}

/* Loading */
.landing-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-3);
  padding: var(--spacing-16);
  color: var(--text-muted);
  font-size: var(--text-sm);
}

.landing-loading i {
  font-size: 1.5rem;
}

/* Projects Grid */
.projects-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: var(--spacing-5);
}

/* Project Card */
.project-card {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xl);
  padding: var(--spacing-5);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
  transition: border-color var(--duration-200), box-shadow var(--duration-200);
}

.project-card:hover {
  border-color: var(--color-info);
  box-shadow: var(--shadow-md);
}

.project-card:focus-visible {
  outline: 2px solid var(--color-info);
  outline-offset: 2px;
}

.project-card--syncing {
  border-color: var(--color-warning);
}

.project-card--error {
  border-color: var(--color-error);
}

/* Add Project Card */
.project-card--add {
  border-style: dashed;
  border-color: var(--border-default);
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: var(--text-muted);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  gap: var(--spacing-2);
}

.project-card--add i {
  font-size: 1.5rem;
}

.project-card--add:hover {
  border-color: var(--color-info);
  color: var(--color-info);
}

/* Card Header */
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-icon {
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

.card-badges {
  display: flex;
  gap: var(--spacing-2);
  flex-wrap: wrap;
}

/* Badges — match SourceManager styles */
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

/* Card Body */
.card-body {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.card-name {
  font-weight: var(--font-semibold);
  font-size: var(--text-base);
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-meta {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  flex-wrap: wrap;
}

.card-repo {
  color: var(--text-secondary);
  font-size: var(--text-xs);
  font-family: var(--font-mono, monospace);
  display: flex;
  align-items: center;
  gap: 0.3rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 220px;
}

.card-branch {
  color: var(--text-muted);
  font-size: var(--text-xs);
  display: flex;
  align-items: center;
  gap: 0.2rem;
}

/* Error */
.card-error {
  font-size: var(--text-xs);
  color: var(--color-error);
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-1-5);
  background: rgba(239, 68, 68, 0.08);
  padding: var(--spacing-2) var(--spacing-3);
  border-radius: var(--radius-md);
}

/* Timestamps */
.card-timestamps {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1-5);
  border-top: 1px solid var(--border-subtle);
  padding-top: var(--spacing-3);
  margin-top: auto;
}

.timestamp-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.timestamp-row > i {
  width: 1rem;
  text-align: center;
  color: var(--text-muted);
  flex-shrink: 0;
}

.timestamp-text {
  flex: 1;
  min-width: 0;
}

.timestamp-text--muted {
  color: var(--text-muted);
  font-style: italic;
}

.commit-link {
  font-family: var(--font-mono, monospace);
  font-size: var(--text-xs);
  color: var(--color-info);
  text-decoration: none;
  padding: 0.1rem var(--spacing-1-5);
  background: rgba(59, 130, 246, 0.1);
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}

.commit-link:hover {
  text-decoration: underline;
  background: rgba(59, 130, 246, 0.2);
}

.commit-hash {
  font-family: var(--font-mono, monospace);
  font-size: var(--text-xs);
  color: var(--text-muted);
  padding: 0.1rem var(--spacing-1-5);
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}

/* Card Actions (#1468) */
.card-actions {
  display: flex;
  gap: var(--spacing-2);
  justify-content: flex-end;
}

.btn-card-action {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  color: var(--text-muted);
  cursor: pointer;
  padding: var(--spacing-1-5) var(--spacing-2);
  font-size: var(--text-xs);
  display: flex;
  align-items: center;
  transition: all var(--duration-200);
}

.btn-card-action:hover:not(:disabled) {
  background: var(--bg-hover);
}

.btn-card-action:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-card-action--sync:hover:not(:disabled) {
  color: var(--color-info);
  border-color: var(--color-info);
}

.btn-card-action--delete:hover:not(:disabled) {
  color: var(--color-error);
  border-color: var(--color-error);
}
</style>
