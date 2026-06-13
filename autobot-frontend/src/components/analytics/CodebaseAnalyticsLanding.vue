<template>
  <div class="analytics-landing">
    <!-- Header -->
    <div class="landing-header">
      <div class="landing-header-text">
        <h1 class="landing-title">
          <Icon name="chart-bar" />
          {{ $t('analytics.codebase.title') }}
        </h1>
        <p class="landing-subtitle">{{ $t('analytics.codebase.landing.subtitle') }}</p>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="landing-loading">
      <Icon name="spinner" class="animate-spin" />
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
            <i :class="source.source_type === 'github' ? 'github' : 'folder'"></i>
          </div>
          <div class="card-badges">
            <span class="status-badge" :class="`status-badge--${source.status}`">
              <Icon :name="getStatusIcon(source.status)" />
              {{ source.status }}
            </span>
            <span class="access-badge" :class="`access-badge--${source.access}`">
              <Icon :name="getAccessIcon(source.access)" />
              {{ source.access }}
            </span>
          </div>
        </div>

        <!-- Card Body -->
        <div class="card-body">
          <div class="card-name">{{ source.name }}</div>
          <div class="card-meta">
            <span v-if="source.repo" class="card-repo">
              <Icon name="link" /> {{ source.repo }}
            </span>
            <span v-else-if="source.clone_path" class="card-repo">
              <Icon name="folder-open" /> {{ source.clone_path }}
            </span>
            <span v-if="source.branch" class="card-branch">
              <Icon name="code-branch" /> {{ source.branch }}
            </span>
          </div>
        </div>

        <!-- Error Message -->
        <div v-if="source.status === 'error' && source.error_message" class="card-error">
          <Icon name="exclamation-circle" />
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
            <i :class="syncingId === source.id ? 'fas fa-spinner fa-spin' : 'sync-alt'"></i>
          </button>
          <button
            class="btn-card-action btn-card-action--delete"
            :disabled="deletingId === source.id"
            :title="$t('analytics.sources.deleteTitle')"
            @click="deleteSource(source)"
          >
            <i :class="deletingId === source.id ? 'fas fa-spinner fa-spin' : 'trash-alt'"></i>
          </button>
        </div>

        <!-- Timestamps -->
        <div class="card-timestamps">
          <div class="timestamp-row">
            <Icon name="sync-alt" />
            <span v-if="source.last_synced" class="timestamp-text">
              {{ $t('analytics.sources.synced') }} {{ formatRelativeTime(source.last_synced) }}
            </span>
            <span v-else class="timestamp-text timestamp-text--muted">
              {{ $t('analytics.sources.neverSynced') }}
            </span>
          </div>
          <div class="timestamp-row">
            <Icon name="database" />
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
            <Icon name="code-branch" />
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
          <div v-if="summaries[source.id]?.last_commit?.message" class="commit-message-row">
            <span class="commit-message">{{ summaries[source.id].last_commit!.message }}</span>
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
        <Icon name="plus" />
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

import type { IconName } from '@/components/ui/Icon.vue'
import Icon from '@/components/ui/Icon.vue'
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import { useSourcesListEndpoint } from '@/composables/analytics/useSourcesListEndpoint'
import { usePollingJob } from '@/composables/usePollingJob'
import { createLogger } from '@/utils/debugUtils'
import AddSourceModal from '@/components/analytics/AddSourceModal.vue'

const logger = createLogger('CodebaseAnalyticsLanding')
const router = useRouter()
const { t } = useI18n()

// ---- Types ----------------------------------------------------------------

import type { CodeSource } from '@/types/analytics'

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

// #5276: `sources` + `loadSources` delegated to the shared
// `useSourcesListEndpoint` composable (was duplicated with
// `useSourceRegistry.ts`).
const {
  sources,
  loadSources: _loadSourcesEndpoint,
  error: sourcesEndpointError,
} = useSourcesListEndpoint()
const summaries = ref<Record<string, SourceSummary>>({})
const loading = ref(false)
const showAddModal = ref(false)
const syncingId = ref<string | null>(null)
const deletingId = ref<string | null>(null)

// Polling for syncing cards (#3092): 4s interval, 5min timeout (75 attempts)
const POLL_INTERVAL_MS = 4000
const POLL_MAX_ATTEMPTS = 75 // 5 minutes / 4s

const _sourcePoller = usePollingJob<void>(
  async (_taskId) => {
    await _loadSourcesEndpoint()
    if (sourcesEndpointError.value) {
      logger.warn('Poll request failed:', sourcesEndpointError.value)
    }
  },
  {
    intervalMs: POLL_INTERVAL_MS,
    maxAttempts: POLL_MAX_ATTEMPTS,
    isComplete: () => !_hasSyncingSource(),
    onDone: async () => {
      await loadSummaries()
      logger.info('All sources resolved — polling complete')
    },
  }
)

// ---- Endpoint composables (#5153 B) --------------------------------------

const summariesEndpoint = useFetchEndpoint<
  { summaries?: Record<string, SourceSummary> },
  Record<string, SourceSummary>
>({
  path: '/api/analytics/codebase/sources/summary',
  label: 'Sources summary',
  pickData: (r) => r.summaries ?? {},
  onSuccess: (map) => {
    summaries.value = map
  },
})

// ---- Data Loading ---------------------------------------------------------

async function loadSources() {
  loading.value = true
  try {
    await _loadSourcesEndpoint()
    await loadSummaries()
  } finally {
    loading.value = false
  }
}

async function loadSummaries() {
  await summariesEndpoint.load()
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

// ---- Source Actions (#1468, #5153 B) ---------------------------------------
// Per-source endpoints: path contains the source id, so construct the
// endpoint instance inside the wrapper function (same pattern as
// useWorkflowTemplates.fetchTemplateDetail).

async function syncSource(source: CodeSource) {
  syncingId.value = source.id
  const syncEndpoint = useFetchEndpoint<unknown, true>({
    path: `/api/analytics/codebase/sources/${source.id}/sync`,
    method: 'POST',
    pickData: () => true,
    onSuccess: () => {
      logger.info('Sync started for source:', source.name)
    },
    onResponse: async (response) => {
      const text = await response.text().catch(() => '')
      return `HTTP ${response.status}${text ? `: ${text}` : ''}`
    },
    label: 'Source sync',
  })
  try {
    await syncEndpoint.load()
    if (!syncEndpoint.error.value) {
      await loadSources()
      _startPolling()
    }
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
  const deleteEndpoint = useFetchEndpoint<unknown, true>({
    path: `/api/analytics/codebase/sources/${source.id}`,
    method: 'DELETE',
    pickData: () => true,
    onSuccess: () => {
      logger.info('Deleted source:', source.name)
    },
    onResponse: async (response) => {
      const text = await response.text().catch(() => '')
      return `HTTP ${response.status}${text ? `: ${text}` : ''}`
    },
    label: 'Source delete',
  })
  try {
    await deleteEndpoint.load()
    if (!deleteEndpoint.error.value) {
      await loadSources()
    }
  } finally {
    deletingId.value = null
  }
}

// ---- Polling (#3092) -------------------------------------------------------

function _hasSyncingSource(): boolean {
  return sources.value.some((s) => s.status === 'syncing')
}

function _startPolling(): void {
  logger.info('Status polling started (interval %dms, timeout 5min)', POLL_INTERVAL_MS)
  _sourcePoller.start('')
}

// ---- Modal Handlers -------------------------------------------------------

function handleSourceSaved() {
  showAddModal.value = false
  loadSources().then(() => {
    if (_hasSyncingSource()) {
      _startPolling()
    }
  })
}

// ---- Lifecycle ------------------------------------------------------------

onMounted(() => {
  loadSources().then(() => {
    if (_hasSyncingSource()) {
      _startPolling()
    }
  })
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
  margin: var(--spacing-0);
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
  font-size: var(--text-2xl);
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
  font-size: var(--text-2xl);
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
  gap: var(--spacing-micro-4);
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
  gap: var(--spacing-micro-3);
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

.commit-message-row {
  margin-top: var(--spacing-1);
  padding-left: calc(var(--spacing-2) + 1em);
}

.commit-message {
  font-size: var(--text-xs);
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
  max-width: 100%;
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
