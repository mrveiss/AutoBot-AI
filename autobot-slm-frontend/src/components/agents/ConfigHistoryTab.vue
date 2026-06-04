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
          placeholder="e.g. orchestrator, chat, rag..."
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

    <div v-else-if="revisions.length === 0 && entityId" class="empty-state">
      No revisions found for {{ entityType }}/{{ entityId }}
    </div>

    <!-- Revision list -->
    <div v-else-if="revisions.length" class="revisions-layout">
      <div class="revisions-list">
        <h3>Revision History ({{ revisions.length }})</h3>
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
          <div v-if="rev.changed_keys.length" class="changed-keys">
            Changed: {{ rev.changed_keys.join(', ') }}
          </div>
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
                {{ rollbackLoading ? 'Rolling back...' : 'Yes, rollback' }}
              </button>
              <button class="btn-cancel" @click="showRollbackConfirm = false">
                {{ $t('agents.configHistoryTab.cancel') }}
              </button>
            </template>
          </div>
        </div>

        <div class="diff-meta">
          <span><strong>Source:</strong> {{ selectedRevision.source }}</span>
          <span><strong>By:</strong> {{ selectedRevision.created_by }}</span>
          <span><strong>At:</strong> {{ formatTime(selectedRevision.created_at) }}</span>
          <span v-if="selectedRevision.changed_keys.length">
            <strong>Changed:</strong> {{ selectedRevision.changed_keys.join(', ') }}
          </span>
        </div>

        <div class="diff-content">
          <div class="diff-column">
            <h4>Before</h4>
            <pre class="json-view">{{ formatJson(selectedRevision.before_config) }}</pre>
          </div>
          <div class="diff-column">
            <h4>After</h4>
            <pre class="json-view">{{ formatJson(selectedRevision.after_config) }}</pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.selector-bar { display: flex; align-items: flex-end; gap: 16px; margin-bottom: 24px; background: white; padding: 16px 20px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.selector-group { display: flex; flex-direction: column; gap: 4px; }
.selector-group label { font-size: 13px; font-weight: 500; color: var(--text-secondary, #6b7280); }
.selector-group select, .selector-group input { padding: 8px 12px; border: 1px solid #d1d5db; border-radius: 8px; font-size: 14px; min-width: 180px; }
.btn-primary { background: #6366f1; color: white; border: none; padding: 8px 16px; border-radius: 6px; font-size: 14px; font-weight: 500; cursor: pointer; }
.btn-primary:hover { background: #4f46e5; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.revisions-layout { display: grid; grid-template-columns: 400px 1fr; gap: 24px; }
.revisions-list { background: white; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); padding: 20px; max-height: 700px; overflow-y: auto; }
.revisions-list h3 { font-size: 18px; font-weight: 600; margin: 0 0 16px 0; color: var(--text-primary, #1a1a2e); }
.revision-item { padding: 12px; border-radius: 8px; cursor: pointer; margin-bottom: 4px; border: 1px solid transparent; }
.revision-item:hover { background: #f3f4f6; }
.revision-item.selected { background: #e0e7ff; border-color: #6366f1; }
.revision-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.source-badge { font-size: 10px; padding: 2px 8px; border-radius: 4px; font-weight: 600; text-transform: uppercase; }
.badge-blue { background: #dbeafe; color: #2563eb; }
.badge-orange { background: #ffedd5; color: #ea580c; }
.badge-gray { background: #f3f4f6; color: #6b7280; }
.revision-by { font-size: 13px; font-weight: 500; color: var(--text-primary, #1a1a2e); }
.revision-time { font-size: 11px; color: var(--text-secondary, #6b7280); margin-left: auto; }
.changed-keys { font-size: 12px; color: var(--text-secondary, #6b7280); margin-top: 4px; }
.diff-panel { background: white; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); padding: 20px; }
.diff-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.diff-header h3 { font-size: 18px; font-weight: 600; margin: 0; color: var(--text-primary, #1a1a2e); }
.diff-actions { display: flex; align-items: center; gap: 8px; }
.btn-rollback { background: #f59e0b; color: white; border: none; padding: 6px 14px; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; }
.btn-rollback:hover { background: #d97706; }
.btn-confirm { background: #ef4444; color: white; border: none; padding: 6px 14px; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; }
.btn-cancel { background: #e5e7eb; color: #374151; border: none; padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; }
.confirm-text { font-size: 13px; color: #ef4444; font-weight: 500; }
.diff-meta { display: flex; gap: 20px; flex-wrap: wrap; font-size: 13px; color: var(--text-secondary, #6b7280); margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb; }
.diff-content { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.diff-column h4 { font-size: 14px; font-weight: 600; margin: 0 0 8px 0; color: var(--text-primary, #1a1a2e); }
.json-view { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; font-family: 'IBM Plex Mono', monospace; font-size: 12px; line-height: 1.5; overflow-x: auto; max-height: 500px; overflow-y: auto; white-space: pre-wrap; word-break: break-word; }
.error-banner { background: #fee2e2; border: 1px solid #ef4444; color: #b91c1c; padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center; }
.loading { text-align: center; color: var(--text-secondary, #6b7280); padding: 60px; }
.empty-state { text-align: center; color: var(--text-secondary, #6b7280); padding: 60px; }
</style>
