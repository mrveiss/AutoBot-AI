<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!-- Issue #9049 - Plugin capability audit log -->

<template>
  <div class="capability-audit-log">
    <div class="audit-header">
      <h2>{{ $t('plugins.capabilities.auditLogTitle') }}</h2>
      <div class="audit-controls">
        <input
          v-model="filterPluginName"
          type="text"
          class="filter-input"
          :placeholder="$t('plugins.capabilities.filterByPlugin')"
        />
        <button class="btn-refresh" @click="fetchAuditLog" :disabled="loading">
          <svg
            class="refresh-icon"
            :class="{ spinning: loading }"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
        </button>
      </div>
    </div>

    <div v-if="loading && entries.length === 0" class="loading-state">
      <svg class="spinner" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path
          class="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
        />
      </svg>
      <span>{{ $t('plugins.capabilities.loadingAudit') }}</span>
    </div>

    <div v-else-if="error" class="error-banner">
      <svg fill="currentColor" viewBox="0 0 20 20">
        <path
          fill-rule="evenodd"
          d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
          clip-rule="evenodd"
        />
      </svg>
      <span>{{ error }}</span>
    </div>

    <div v-else-if="filteredEntries.length === 0" class="empty-state">
      <svg class="empty-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="1.5"
          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
        />
      </svg>
      <p>{{ $t('plugins.capabilities.noAuditEntries') }}</p>
    </div>

    <div v-else>
      <BaseTable :columns="auditColumns" :rows="auditRows" size="compact" :aria-label="$t('plugins.capabilities.auditLogTitle')">
        <template #cell-granted="{ row }">
          <BaseBadge size="sm" :variant="row.granted ? 'success' : 'error'">
            {{ row.granted ? $t('plugins.capabilities.granted') : $t('plugins.capabilities.denied') }}
          </BaseBadge>
        </template>
      </BaseTable>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseBadge, BaseTable, type BaseTableColumn } from '@autobot/ui'
import { usePlugins, type AuditLogEntry } from '@/composables/usePlugins'

const { getAuditLog } = usePlugins()
const { t } = useI18n()

const loading = ref(false)
const error = ref<string | null>(null)
const entries = ref<AuditLogEntry[]>([])
const filterPluginName = ref('')

// #17562: the audit log is the kit table; the status cell is a kit badge.
const auditColumns = computed<BaseTableColumn[]>(() => [
  { key: 'when', label: t('plugins.capabilities.timestamp'), monospace: true },
  { key: 'plugin_name', label: t('plugins.capabilities.plugin') },
  { key: 'capability', label: t('plugins.capabilities.capability'), monospace: true },
  { key: 'operation', label: t('plugins.capabilities.operation') },
  { key: 'granted', label: t('plugins.capabilities.status') },
])
const auditRows = computed(() =>
  filteredEntries.value.map((entry, index) => ({ ...entry, id: index, when: formatTimestamp(entry.timestamp) })),
)

const filteredEntries = computed(() => {
  if (!filterPluginName.value) {
    return entries.value
  }
  const filter = filterPluginName.value.toLowerCase()
  return entries.value.filter(entry =>
    entry.plugin_name.toLowerCase().includes(filter)
  )
})

async function fetchAuditLog() {
  loading.value = true
  error.value = null
  try {
    const data = await getAuditLog(100)
    entries.value = data
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to fetch audit log'
  } finally {
    loading.value = false
  }
}

function formatTimestamp(timestamp: string): string {
  try {
    const date = new Date(timestamp)
    return date.toLocaleString()
  } catch {
    return timestamp
  }
}

onMounted(() => {
  fetchAuditLog()
})
</script>

<style scoped>
.capability-audit-log {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.audit-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 1rem;
}

.audit-header h2 {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
}

.audit-controls {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.filter-input {
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background-color: var(--bg-primary);
  color: var(--text-primary);
  font-size: 0.875rem;
  min-width: 200px;
}

.filter-input:focus {
  outline: none;
  border-color: var(--color-primary);
}

.btn-refresh {
  padding: 0.5rem;
  background: none;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.2s;
}

.btn-refresh:hover:not(:disabled) {
  background-color: var(--color-background-hover);
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.btn-refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.refresh-icon {
  width: var(--spacing-5);
  height: var(--spacing-5);
}

.refresh-icon.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  padding: 3rem;
  color: var(--text-secondary);
}

.spinner {
  width: var(--spacing-6);
  height: var(--spacing-6);
  animation: spin 1s linear infinite;
}

.error-banner {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  background-color: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: var(--radius-md);
  color: var(--color-error);
}

.error-banner svg {
  width: var(--spacing-5);
  height: var(--spacing-5);
  flex-shrink: 0;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem;
  color: var(--text-secondary);
}

.empty-icon {
  width: var(--spacing-12);
  height: var(--spacing-12);
  margin-bottom: 1rem;
  opacity: 0.5;
}
</style>
