<!--
AutoBot - AI-Powered Automation Platform
Copyright (c) 2025 mrveiss
Author: mrveiss

MemoryPrivacyPanel.vue - Memory transparency, forget, and export controls
Issue #10554: Per-user memory transparency + edit/forget-everywhere + export
-->

<template>
  <div class="memory-privacy-panel">
    <div class="panel-header">
      <h3 class="panel-title">
        <Icon name="brain" aria-hidden="true" />
        {{ t('settings.memoryPrivacy.title') }}
      </h3>
      <p class="panel-desc">
        {{ t('settings.memoryPrivacy.description') }}
      </p>
    </div>

    <!-- Toolbar -->
    <div class="toolbar">
      <button class="btn btn-primary" :disabled="loading" @click="loadMemories">
        <Icon :name="loading ? 'sync-alt' : 'sync'" :spin="loading" aria-hidden="true" />
        {{ loading ? t('settings.memoryPrivacy.loading') : t('settings.memoryPrivacy.refresh') }}
      </button>
      <button class="btn btn-secondary" :disabled="exporting" @click="downloadExport">
        <Icon :name="exporting ? 'sync-alt' : 'download'" :spin="exporting" aria-hidden="true" />
        {{ exporting ? t('settings.memoryPrivacy.preparing') : t('settings.memoryPrivacy.exportJson') }}
      </button>
    </div>

    <!-- Summary bar -->
    <div v-if="memories.length > 0" class="summary-bar">
      <span class="total-badge">{{ t('settings.memoryPrivacy.itemCount', { count: memories.length }) }}</span>
      <span v-for="(count, store) in storeCounts" :key="store" class="store-badge">
        {{ store }}: {{ count }}
      </span>
    </div>

    <!-- Empty state -->
    <div v-if="!loading && memories.length === 0 && loaded" class="empty-state">
      <Icon name="check-circle" aria-hidden="true" />
      {{ t('settings.memoryPrivacy.emptyState') }}
    </div>

    <!-- Memory list -->
    <ul v-if="memories.length > 0" class="memory-list" :aria-label="t('settings.memoryPrivacy.listLabel')">
      <li
        v-for="item in memories"
        :key="item.memory_id"
        class="memory-item"
        :class="{ 'is-deleting': deletingIds.has(item.memory_id) }"
      >
        <div class="item-header">
          <span class="store-tag" :data-store="item.store">{{ item.store }}</span>
          <span class="item-ts">{{ formatTs(item.timestamp) }}</span>
        </div>
        <p class="item-content">{{ item.content || t('settings.memoryPrivacy.noPreview') }}</p>
        <details v-if="item.provenance && Object.keys(item.provenance).length > 0" class="provenance">
          <summary>{{ t('settings.memoryPrivacy.provenance') }}</summary>
          <pre class="provenance-data">{{ JSON.stringify(item.provenance, null, 2) }}</pre>
        </details>
        <div class="item-actions">
          <button
            class="btn btn-danger btn-sm"
            :disabled="deletingIds.has(item.memory_id)"
            @click="forgetItem(item)"
            :aria-label="t('settings.memoryPrivacy.forgetAriaLabel', { store: item.store })"
          >
            <Icon name="trash" aria-hidden="true" />
            {{ t('settings.memoryPrivacy.forget') }}
          </button>
          <button
            class="btn btn-ghost btn-sm"
            :disabled="deletingIds.has(item.memory_id)"
            @click="forgetEverywhere(item)"
            :aria-label="t('settings.memoryPrivacy.forgetEverywhereAriaLabel', { id: item.memory_id })"
          >
            <Icon name="times-circle" aria-hidden="true" />
            {{ t('settings.memoryPrivacy.forgetEverywhere') }}
          </button>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { createLogger } from '@/utils/debugUtils'
import { useNotificationBus } from '@/composables/useNotificationBus'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import Icon from '@/components/ui/Icon.vue'
import apiClient from '@/utils/ApiClient'

const logger = createLogger('MemoryPrivacyPanel')
const { t } = useI18n()
const { showToast } = useNotificationBus()
const { confirm } = useConfirmDialog()

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

interface MemoryItem {
  memory_id: string
  store: string
  content: string
  provenance: Record<string, unknown>
  timestamp: string
}

const memories = ref<MemoryItem[]>([])
const loading = ref(false)
const exporting = ref(false)
const loaded = ref(false)
const deletingIds = ref<Set<string>>(new Set())

// ---------------------------------------------------------------------------
// Computed
// ---------------------------------------------------------------------------

const storeCounts = computed(() => {
  const counts: Record<string, number> = {}
  for (const m of memories.value) {
    counts[m.store] = (counts[m.store] || 0) + 1
  }
  return counts
})

// ---------------------------------------------------------------------------
// Methods
// ---------------------------------------------------------------------------

function formatTs(ts: string): string {
  if (!ts) return ''
  try {
    return new Date(ts).toLocaleString()
  } catch {
    return ts
  }
}

async function loadMemories() {
  loading.value = true
  loaded.value = false
  try {
    const data = await apiClient.get<{ memories: MemoryItem[] }>('/memory/privacy/list')
    memories.value = data.memories || []
    loaded.value = true
    logger.debug('MemoryPrivacyPanel: loaded %d items', memories.value.length)
  } catch (err) {
    logger.warn('MemoryPrivacyPanel: load failed', err)
    showToast(t('settings.memoryPrivacy.loadFailed'), 'error')
    loaded.value = true
  } finally {
    loading.value = false
  }
}

async function forgetItem(item: MemoryItem) {
  const ok = await confirm({
    title: t('settings.memoryPrivacy.forgetConfirmTitle'),
    message: t('settings.memoryPrivacy.forgetConfirmMessage', { store: item.store }),
  })
  if (!ok) return
  deletingIds.value = new Set([...deletingIds.value, item.memory_id])
  try {
    await apiClient.delete(`/memory/privacy/${item.store}/${encodeURIComponent(item.memory_id)}`)
    memories.value = memories.value.filter(m => m.memory_id !== item.memory_id)
    showToast(t('settings.memoryPrivacy.forgotten'), 'success')
    logger.info('MemoryPrivacyPanel: forgot %s from %s', item.memory_id, item.store)
  } catch (err) {
    logger.warn('MemoryPrivacyPanel: forget failed', err)
    showToast(t('settings.memoryPrivacy.forgetFailed'), 'error')
  } finally {
    const next = new Set(deletingIds.value)
    next.delete(item.memory_id)
    deletingIds.value = next
  }
}

async function forgetEverywhere(item: MemoryItem) {
  const ok = await confirm({
    title: t('settings.memoryPrivacy.forgetEverywhereConfirmTitle'),
    message: t('settings.memoryPrivacy.forgetEverywhereConfirmMessage'),
  })
  if (!ok) return
  deletingIds.value = new Set([...deletingIds.value, item.memory_id])
  try {
    const result = await apiClient.delete<{ deleted_from: string[] }>(
      `/memory/privacy/forget-everywhere/${encodeURIComponent(item.memory_id)}`
    )
    memories.value = memories.value.filter(m => m.memory_id !== item.memory_id)
    const from = (result.deleted_from || []).join(', ') || t('settings.memoryPrivacy.noStores')
    showToast(t('settings.memoryPrivacy.forgottenFrom', { stores: from }), 'success')
    logger.info('MemoryPrivacyPanel: forget-everywhere %s → %s', item.memory_id, from)
  } catch (err) {
    logger.warn('MemoryPrivacyPanel: forget-everywhere failed', err)
    showToast(t('settings.memoryPrivacy.forgetEverywhereFailed'), 'error')
  } finally {
    const next = new Set(deletingIds.value)
    next.delete(item.memory_id)
    deletingIds.value = next
  }
}

async function downloadExport() {
  exporting.value = true
  try {
    // ApiClient.get returns parsed JSON directly — no axios envelope.
    const data = await apiClient.get<Record<string, unknown>>('/memory/privacy/export')
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'memory_export.json'
    a.click()
    URL.revokeObjectURL(url)
    showToast(t('settings.memoryPrivacy.exportDownloaded'), 'success')
    logger.info('MemoryPrivacyPanel: export downloaded')
  } catch (err) {
    logger.warn('MemoryPrivacyPanel: export failed', err)
    showToast(t('settings.memoryPrivacy.exportFailed'), 'error')
  } finally {
    exporting.value = false
  }
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onMounted(loadMemories)
</script>

<style scoped>
.memory-privacy-panel {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md, 1rem);
}

.panel-header {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs, 0.25rem);
}

.panel-title {
  font-size: 1rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0;
}

.panel-desc {
  font-size: 0.875rem;
  color: var(--text-secondary, #888);
  margin: 0;
}

.toolbar {
  display: flex;
  gap: var(--spacing-sm, 0.5rem);
  flex-wrap: wrap;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.45rem 0.9rem;
  border: 1px solid transparent;
  border-radius: var(--radius-sm, 4px);
  font-size: 0.875rem;
  cursor: pointer;
  transition: opacity 0.15s;
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: var(--color-primary, #4f8ef7); color: #fff; }
.btn-secondary { background: var(--surface-secondary, #333); color: var(--text-primary, #eee); }
.btn-danger { background: var(--color-danger, #e24848); color: #fff; }
.btn-ghost { background: transparent; color: var(--text-secondary, #aaa); border-color: var(--border-color, #444); }
.btn-sm { padding: 0.3rem 0.65rem; font-size: 0.8rem; }

.summary-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  font-size: 0.8rem;
}
.total-badge { font-weight: 600; color: var(--text-primary, #eee); }
.store-badge {
  padding: 0.15rem 0.5rem;
  background: var(--surface-secondary, #333);
  border-radius: 999px;
  color: var(--text-secondary, #aaa);
}

.empty-state {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--text-secondary, #888);
  font-size: 0.9rem;
  padding: 1rem 0;
}

.memory-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.memory-item {
  padding: 0.75rem 1rem;
  background: var(--surface-secondary, #2a2a2a);
  border: 1px solid var(--border-color, #3a3a3a);
  border-radius: var(--radius-md, 6px);
  transition: opacity 0.2s;
}
.memory-item.is-deleting { opacity: 0.4; pointer-events: none; }

.item-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.4rem;
}

.store-tag {
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  background: var(--color-primary-muted, #1e3a5f);
  color: var(--color-primary, #4f8ef7);
}

.item-ts {
  font-size: 0.75rem;
  color: var(--text-muted, #666);
  margin-left: auto;
}

.item-content {
  font-size: 0.875rem;
  color: var(--text-primary, #ddd);
  margin: 0 0 0.5rem;
  word-break: break-word;
  white-space: pre-wrap;
  max-height: 6rem;
  overflow-y: auto;
}

.provenance { margin-bottom: 0.5rem; }
.provenance summary { font-size: 0.8rem; cursor: pointer; color: var(--text-secondary, #888); }
.provenance-data {
  font-size: 0.75rem;
  background: var(--surface-tertiary, #1a1a1a);
  padding: 0.5rem;
  border-radius: 4px;
  overflow-x: auto;
  margin-top: 0.25rem;
}

.item-actions {
  display: flex;
  gap: 0.4rem;
  flex-wrap: wrap;
}
</style>
