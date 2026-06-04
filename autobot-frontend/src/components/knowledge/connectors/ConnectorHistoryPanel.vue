<script setup lang="ts">
/**
 * ConnectorHistoryPanel — per-connector sync history + live progress indicator.
 *
 * Issue #8149: shows past syncs with status badges, duration, source counts,
 * expandable per-source errors, and a live progress bar while a sync is
 * in-flight (polls every 5s, stops on terminal status).
 */

import { ref, computed, onMounted, watch } from 'vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import { useConnectorJob, fetchConnectorHistory } from '@/composables/knowledge/useConnectorJob'
import { formatTimeAgo } from '@/utils/formatHelpers'
import { createLogger } from '@/utils/debugUtils'
import type { ConnectorHistoryEntry } from '@/types/knowledgeBase'

const logger = createLogger('ConnectorHistoryPanel')

const props = defineProps<{
  connectorId: string
  /** When true, immediately start polling for in-flight job state. */
  syncActive?: boolean
}>()

const emit = defineEmits<{
  close: []
}>()

const history = ref<ConnectorHistoryEntry[]>([])
const historyLoading = ref(false)
const expandedRows = ref<Set<number>>(new Set())

const { jobState, isPolling, start: startPoll, stop: stopPoll } = useConnectorJob()

async function loadHistory() {
  historyLoading.value = true
  try {
    history.value = await fetchConnectorHistory(props.connectorId)
  } catch (err) {
    logger.error('Failed to load history', err)
  } finally {
    historyLoading.value = false
  }
}

onMounted(() => {
  loadHistory()
  if (props.syncActive) {
    startPoll(props.connectorId)
  }
})

watch(() => props.syncActive, (active) => {
  if (active) startPoll(props.connectorId)
  else stopPoll()
})

watch(isPolling, (active) => {
  if (!active && jobState.value && jobState.value.status !== 'running') {
    loadHistory()
  }
})

function toggleRow(index: number) {
  if (expandedRows.value.has(index)) {
    expandedRows.value.delete(index)
  } else {
    expandedRows.value.add(index)
  }
}

function statusVariant(status: string | null): 'success' | 'error' | 'warning' | 'default' {
  switch (status) {
    case 'success': return 'success'
    case 'failed': return 'error'
    case 'partial': return 'warning'
    default: return 'default'
  }
}

const progressPercent = computed(() => {
  const j = jobState.value
  if (!j || j.sources_total === 0) return 0
  return Math.round((j.sources_done / j.sources_total) * 100)
})

function errorList(entry: ConnectorHistoryEntry): string[] {
  if (!entry.errors) return []
  if (Array.isArray(entry.errors)) return entry.errors
  return []
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) return '—'
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}m ${s}s`
}
</script>

<template>
  <div class="history-panel">
    <div class="panel-header">
      <h3 class="panel-title">Sync History</h3>
      <button class="close-btn" aria-label="Close" @click="emit('close')">✕</button>
    </div>

    <!-- Live job progress -->
    <div v-if="isPolling || (jobState && jobState.status === 'running')" class="live-job">
      <div class="live-header">
        <BaseBadge variant="warning" size="xs">Running</BaseBadge>
        <span class="live-worker">{{ jobState?.worker_id }}</span>
      </div>
      <div class="progress-bar-track" role="progressbar" :aria-valuenow="progressPercent" aria-valuemin="0" aria-valuemax="100">
        <div class="progress-bar-fill" :style="{ width: progressPercent + '%' }" />
      </div>
      <div class="live-counts">
        {{ jobState?.sources_done ?? 0 }} / {{ jobState?.sources_total ?? '?' }} sources
        <span v-if="jobState && jobState.sources_failed > 0" class="failed-count">
          ({{ jobState.sources_failed }} failed)
        </span>
      </div>
    </div>

    <!-- History list -->
    <div v-if="historyLoading" class="loading-state">Loading…</div>
    <div v-else-if="history.length === 0" class="empty-state">No sync history yet.</div>
    <ul v-else class="history-list">
      <li
        v-for="(entry, idx) in history"
        :key="idx"
        class="history-row"
        :class="{ expanded: expandedRows.has(idx) }"
      >
        <div class="row-main" @click="errorList(entry).length > 0 && toggleRow(idx)">
          <BaseBadge :variant="statusVariant(entry.status)" size="xs">
            {{ entry.status ?? '?' }}
          </BaseBadge>
          <span class="row-time">{{ entry.started_at ? formatTimeAgo(entry.started_at) : '?' }}</span>
          <span class="row-duration">{{ formatDuration(entry.duration_seconds) }}</span>
          <span class="row-counts">
            +{{ entry.added ?? 0 }} ~{{ entry.updated ?? 0 }} -{{ entry.deleted ?? 0 }}
          </span>
          <span class="row-sources" v-if="entry.sources_total">
            {{ entry.sources_done ?? 0 }}/{{ entry.sources_total }} src
          </span>
          <span
            v-if="errorList(entry).length > 0"
            class="row-errors"
            :title="'Click to expand ' + errorList(entry).length + ' errors'"
          >
            {{ errorList(entry).length }} err
          </span>
        </div>
        <ul v-if="expandedRows.has(idx) && errorList(entry).length > 0" class="error-list">
          <li v-for="(err, ei) in errorList(entry)" :key="ei" class="error-item">{{ err }}</li>
        </ul>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.history-panel {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-default);
  padding: var(--spacing-4);
  max-height: 480px;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.panel-title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  font-family: var(--font-sans);
  margin: 0;
}

.close-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-tertiary);
  font-size: var(--text-xs);
  padding: var(--spacing-1);
  line-height: 1;
}

/* Live job */
.live-job {
  padding: var(--spacing-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-xs);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.live-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.live-worker {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  font-family: var(--font-mono);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.progress-bar-track {
  height: 6px;
  background: var(--border-default);
  border-radius: 3px;
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  background: var(--color-info);
  border-radius: 3px;
  transition: width 0.4s ease;
}

.live-counts {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  font-family: var(--font-mono);
}

.failed-count {
  color: var(--color-error);
}

/* History list */
.loading-state,
.empty-state {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
  text-align: center;
  padding: var(--spacing-4) 0;
}

.history-list {
  list-style: none;
  padding: 0;
  margin: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.history-row {
  border-radius: var(--radius-xs);
  border: 1px solid var(--border-default);
  overflow: hidden;
}

.row-main {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-3);
  cursor: default;
  font-size: var(--text-xs);
  font-family: var(--font-sans);
}

.history-row.expanded .row-main {
  background: var(--bg-secondary);
}

.row-time {
  color: var(--text-secondary);
  flex: 1;
}

.row-duration {
  color: var(--text-tertiary);
  font-family: var(--font-mono);
  min-width: 48px;
  text-align: right;
}

.row-counts {
  color: var(--text-tertiary);
  font-family: var(--font-mono);
}

.row-sources {
  color: var(--text-tertiary);
  font-family: var(--font-mono);
}

.row-errors {
  color: var(--color-error);
  font-family: var(--font-mono);
  cursor: pointer;
  text-decoration: underline dotted;
}

/* Error expansion */
.error-list {
  list-style: none;
  padding: var(--spacing-2) var(--spacing-3);
  margin: 0;
  background: var(--color-error-bg);
  border-top: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
  max-height: 120px;
  overflow-y: auto;
}

.error-item {
  font-size: var(--text-xs);
  font-family: var(--font-mono);
  color: var(--color-error-dark);
  word-break: break-all;
  line-height: 1.4;
}
</style>
