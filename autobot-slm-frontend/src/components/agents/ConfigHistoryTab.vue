<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Config History Tab (#1404)
 *
 * Timeline of configuration revisions with diff view and rollback.
 * Uses /autobot-api proxy to main backend.
 */

import { computed, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { getBackendUrl } from '@/config/ssot-config'

interface Revision {
  id: string
  entity_type: string
  entity_id: string
  before_config: Record<string, unknown> | null
  after_config: Record<string, unknown>
  changed_keys: string[]
  source: string
  created_by: string
  created_at: string | null
}

const authStore = useAuthStore()
const revisions = ref<Revision[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const selectedRevision = ref<Revision | null>(null)
const showRollbackConfirm = ref(false)
const rollbackLoading = ref(false)

const entityType = ref('agent')
const entityId = ref('')

const entityTypes = [
  { value: 'agent', label: 'Agent' },
  { value: 'system', label: 'System' },
]

const systemEntities = ['settings', 'config', 'backend']

const headers = computed(() => ({
  Authorization: `Bearer ${authStore.token}`,
  'Content-Type': 'application/json',
}))

async function fetchRevisions() {
  if (!entityType.value || !entityId.value) return
  loading.value = true
  error.value = null
  selectedRevision.value = null
  try {
    const res = await fetch(
      `${getBackendUrl()}/config-revisions/${entityType.value}/${entityId.value}?limit=50`,
      { headers: headers.value },
    )
    if (!res.ok) throw new Error(`Failed to load revisions: ${res.status}`)
    revisions.value = await res.json()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load revisions'
    revisions.value = []
  } finally {
    loading.value = false
  }
}

async function rollback(revisionId: string) {
  rollbackLoading.value = true
  try {
    const res = await fetch(
      `${getBackendUrl()}/config-revisions/${entityType.value}/${entityId.value}/${revisionId}/rollback`,
      { method: 'POST', headers: headers.value },
    )
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      throw new Error(data.detail || `Rollback failed: ${res.status}`)
    }
    showRollbackConfirm.value = false
    selectedRevision.value = null
    await fetchRevisions()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Rollback failed'
  } finally {
    rollbackLoading.value = false
  }
}

function selectRevision(rev: Revision) {
  selectedRevision.value = selectedRevision.value?.id === rev.id ? null : rev
  showRollbackConfirm.value = false
}

function formatJson(obj: unknown): string {
  return JSON.stringify(obj, null, 2)
}

function sourceBadgeClass(source: string): string {
  return source === 'rollback' ? 'badge-orange' : source === 'api' ? 'badge-blue' : 'badge-gray'
}

function formatTime(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

watch([entityType, entityId], () => {
  if (entityId.value) fetchRevisions()
})
</script>

<template>
  <div class="config-history-tab">
    <div v-if="error" class="error-banner">
      {{ error }}
      <button @click="error = null">{{ $t('agents.configHistoryTab.dismiss') }}</button>
    </div>

    <!-- Entity selector -->
    <div class="selector-bar">
      <div class="selector-group">
        <label>{{ $t('agents.configHistoryTab.entityType') }}</label>
        <select v-model="entityType">
          <option v-for="t in entityTypes" :key="t.value" :value="t.value">
            {{ t.label }}
          </option>
        </select>
      </div>
      <div class="selector-group">
        <label>{{ $t('agents.configHistoryTab.entityID') }}</label>
        <input
          v-if="entityType === 'agent'"
          v-model="entityId"
          :placeholder="$t('agents.configHistoryTab.eGOrchestratorChatRag')"
        />
        <select v-else v-model="entityId">
          <option value="" disabled>{{ $t('agents.configHistoryTab.select') }}</option>
          <option v-for="e in systemEntities" :key="e" :value="e">{{ e }}</option>
        </select>
      </div>
      <button class="btn-primary" @click="fetchRevisions" :disabled="!entityId">
        {{ $t('agents.configHistoryTab.loadHistory') }}
      </button>
    </div>

    <div v-if="loading" class="loading">{{ $t('agents.configHistoryTab.loadingRevisions') }}</div>

    <div v-else-if="revisions.length === 0 && entityId" class="empty-state">{{ $t('agents.configHistoryTab.noRevisionsFoundForValue0Value1', { value0: entityType, value1: entityId }) }}</div>

    <!-- Revision list -->
    <div v-else-if="revisions.length" class="revisions-layout">
      <div class="revisions-list">
        <h3>{{ $t('agents.configHistoryTab.revisionHistoryCount', { count: revisions.length }) }}</h3>
        <div
          v-for="rev in revisions"
          :key="rev.id"
          class="revision-item"
          :class="{ selected: selectedRevision?.id === rev.id }"
          @click="selectRevision(rev)"
        >
          <div class="revision-meta">
            <span :class="['source-badge', sourceBadgeClass(rev.source)]">{{
              rev.source
            }}</span>
            <span class="revision-by">{{ rev.created_by }}</span>
            <span class="revision-time">{{ formatTime(rev.created_at) }}</span>
          </div>
          <div v-if="rev.changed_keys.length" class="changed-keys">{{ $t('agents.configHistoryTab.changedValue0', { value0: rev.changed_keys.join(', ') }) }}</div>
        </div>
      </div>

      <!-- Diff view -->
      <div v-if="selectedRevision" class="diff-panel">
        <div class="diff-header">
          <h3>{{ $t('agents.configHistoryTab.revisionDetails') }}</h3>
          <div class="diff-actions">
            <button
              v-if="!showRollbackConfirm"
              class="btn-rollback"
              @click="showRollbackConfirm = true"
            >
              {{ $t('agents.configHistoryTab.rollbackToThis') }}
            </button>
            <template v-else>
              <span class="confirm-text">{{ $t('agents.configHistoryTab.confirmRollback') }}</span>
              <button
                class="btn-confirm"
                :disabled="rollbackLoading"
                @click="rollback(selectedRevision!.id)"
              >
                {{ rollbackLoading ? $t('agents.configHistoryTab.rollingBack') : $t('agents.configHistoryTab.yesRollback') }}
              </button>
              <button class="btn-cancel" @click="showRollbackConfirm = false">
                {{ $t('agents.configHistoryTab.cancel') }}
              </button>
            </template>
          </div>
        </div>

        <div class="diff-meta">
          <span><strong>{{ $t('agents.configHistoryTab.source') }}</strong> {{ selectedRevision.source }}</span>
          <span><strong>{{ $t('agents.configHistoryTab.by') }}</strong> {{ selectedRevision.created_by }}</span>
          <span><strong>{{ $t('agents.configHistoryTab.at') }}</strong> {{ formatTime(selectedRevision.created_at) }}</span>
          <span v-if="selectedRevision.changed_keys.length">
            <strong>{{ $t('agents.configHistoryTab.changed') }}</strong> {{ selectedRevision.changed_keys.join(', ') }}
          </span>
        </div>

        <div class="diff-content">
          <div class="diff-column">
            <h4>{{ $t('agents.configHistoryTab.before') }}</h4>
            <pre class="json-view">{{ formatJson(selectedRevision.before_config) }}</pre>
          </div>
          <div class="diff-column">
            <h4>{{ $t('agents.configHistoryTab.after') }}</h4>
            <pre class="json-view">{{ formatJson(selectedRevision.after_config) }}</pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.selector-bar { display: flex; align-items: flex-end; gap: var(--spacing-4); margin-bottom: var(--spacing-6); background: white; padding: var(--spacing-4) var(--spacing-5); border-radius: var(--radius-xl); box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.selector-group { display: flex; flex-direction: column; gap: var(--spacing-1); }
.selector-group label { font-size: 13px; font-weight: 500; color: var(--text-secondary); }
.selector-group select, .selector-group input { padding: var(--spacing-2) var(--spacing-3); border: 1px solid var(--slm-gray-300); border-radius: var(--radius-lg); font-size: var(--text-sm); min-width: 180px; }
.btn-primary { background: var(--slm-indigo-500); color: white; border: none; padding: var(--spacing-2) var(--spacing-4); border-radius: var(--radius-md); font-size: var(--text-sm); font-weight: 500; cursor: pointer; }
.btn-primary:hover { background: var(--slm-indigo-600); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.revisions-layout { display: grid; grid-template-columns: 400px 1fr; gap: var(--spacing-6); }
.revisions-list { background: white; border-radius: var(--radius-xl); box-shadow: 0 1px 3px rgba(0,0,0,0.1); padding: var(--spacing-5); max-height: 700px; overflow-y: auto; }
.revisions-list h3 { font-size: var(--text-lg); font-weight: 600; margin: 0 0 var(--spacing-4) 0; color: var(--text-primary); }
.revision-item { padding: var(--spacing-3); border-radius: var(--radius-lg); cursor: pointer; margin-bottom: var(--spacing-1); border: 1px solid transparent; }
.revision-item:hover { background: var(--slm-gray-100); }
.revision-item.selected { background: var(--slm-indigo-100); border-color: var(--slm-indigo-500); }
.revision-meta { display: flex; align-items: center; gap: var(--spacing-2); flex-wrap: wrap; }
.source-badge { font-size: 10px; padding: 2px var(--spacing-2); border-radius: var(--radius-default); font-weight: 600; text-transform: uppercase; }
.badge-blue { background: var(--slm-blue-100); color: var(--slm-blue-600); }
.badge-orange { background: var(--slm-orange-100); color: var(--slm-orange-600); }
.badge-gray { background: var(--slm-gray-100); color: var(--slm-gray-500); }
.revision-by { font-size: 13px; font-weight: 500; color: var(--text-primary); }
.revision-time { font-size: 11px; color: var(--text-secondary); margin-left: auto; }
.changed-keys { font-size: var(--text-xs); color: var(--text-secondary); margin-top: var(--spacing-1); }
.diff-panel { background: white; border-radius: var(--radius-xl); box-shadow: 0 1px 3px rgba(0,0,0,0.1); padding: var(--spacing-5); }
.diff-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--spacing-4); }
.diff-header h3 { font-size: var(--text-lg); font-weight: 600; margin: 0; color: var(--text-primary); }
.diff-actions { display: flex; align-items: center; gap: var(--spacing-2); }
.btn-rollback { background: var(--slm-amber-500); color: white; border: none; padding: 6px 14px; border-radius: var(--radius-md); font-size: 13px; font-weight: 500; cursor: pointer; }
.btn-rollback:hover { background: var(--slm-amber-600); }
.btn-confirm { background: var(--color-danger-500); color: white; border: none; padding: 6px 14px; border-radius: var(--radius-md); font-size: 13px; font-weight: 500; cursor: pointer; }
.btn-cancel { background: var(--slm-gray-200); color: var(--slm-gray-700); border: none; padding: 6px 14px; border-radius: var(--radius-md); font-size: 13px; cursor: pointer; }
.confirm-text { font-size: 13px; color: var(--color-danger-500); font-weight: 500; }
.diff-meta { display: flex; gap: var(--spacing-5); flex-wrap: wrap; font-size: 13px; color: var(--text-secondary); margin-bottom: var(--spacing-4); padding-bottom: var(--spacing-3); border-bottom: 1px solid var(--slm-gray-200); }
.diff-content { display: grid; grid-template-columns: 1fr 1fr; gap: var(--spacing-4); }
.diff-column h4 { font-size: var(--text-sm); font-weight: 600; margin: 0 0 var(--spacing-2) 0; color: var(--text-primary); }
.json-view { background: var(--slm-gray-50); border: 1px solid var(--slm-gray-200); border-radius: var(--radius-lg); padding: var(--spacing-3); font-family: 'IBM Plex Mono', monospace; font-size: var(--text-xs); line-height: 1.5; overflow-x: auto; max-height: 500px; overflow-y: auto; white-space: pre-wrap; word-break: break-word; }
.error-banner { background: var(--slm-red-100); border: 1px solid var(--color-danger-500); color: var(--slm-red-700); padding: var(--spacing-3) var(--spacing-4); border-radius: var(--radius-lg); margin-bottom: var(--spacing-4); display: flex; justify-content: space-between; align-items: center; }
.loading { text-align: center; color: var(--text-secondary); padding: 60px; }
.empty-state { text-align: center; color: var(--text-secondary); padding: 60px; }
</style>
