<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  Operations View
  Issue #4270 - Wire orphaned OperationDetail component
-->
<template>
  <div class="operations-view">
    <div class="page-header">
      <div class="page-header-content">
        <h2 class="page-title">{{ $t('operations.view.title') }}</h2>
        <p class="page-subtitle">{{ $t('operations.view.subtitle') }}</p>
      </div>
      <div class="header-actions">
        <button class="btn-action-secondary" :disabled="loading" @click="loadOperations()">
          <Icon name="sync-alt" :spin="loading" />
          {{ $t('operations.view.refresh') }}
        </button>
      </div>
    </div>

    <div v-if="error" class="error-banner">
      <Icon name="exclamation-circle" />
      <span>{{ error }}</span>
      <button class="btn-dismiss" @click="error = null">
        <Icon name="times" />
      </button>
    </div>

    <OperationsPanel
      :operations="operations"
      :total-count="totalCount"
      :loading="loading"
      :filter="filter"
      @cancel="handleCancel"
      @resume="handleResume"
      @refresh="handleRefreshOperation"
      @update:filter="handleFilterChange"
      @clear-filter="handleClearFilter"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { createLogger } from '@/utils/debugUtils'
import { useOperationsApi } from '@/composables/useOperationsApi'
import OperationsPanel from '@/components/operations/OperationsPanel.vue'
import Icon from '@/components/ui/Icon.vue'
import type { Operation, OperationsFilter } from '@/types/operations'

const { t } = useI18n()
const logger = createLogger('OperationsView')
const api = useOperationsApi()

const operations = ref<Operation[]>([])
const totalCount = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)
const filter = ref<OperationsFilter>({ limit: 50 })

async function loadOperations() {
  loading.value = true
  error.value = null
  try {
    const result = await api.listOperations(filter.value)
    if (result) {
      operations.value = result.operations
      totalCount.value = result.total_count
    }
  } catch (err) {
    logger.error('Failed to load operations:', err)
    error.value = t('operations.view.loadError')
  } finally {
    loading.value = false
  }
}

async function handleCancel(operationId: string) {
  await api.cancelOperation(operationId)
  await loadOperations()
}

async function handleResume(operationId: string) {
  await api.resumeOperation(operationId)
  await loadOperations()
}

async function handleRefreshOperation(_operationId: string) {
  await loadOperations()
}

function handleFilterChange(newFilter: OperationsFilter) {
  filter.value = newFilter
  loadOperations()
}

function handleClearFilter() {
  filter.value = { limit: 50 }
  loadOperations()
}

onMounted(() => {
  loadOperations()
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.operations-view {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-6);
  padding: var(--spacing-6);
  height: 100%;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--spacing-4);
}

.page-header-content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.page-title {
  font-size: var(--text-2xl);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: var(--spacing-0);
}

.page-subtitle {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
  margin: var(--spacing-0);
}

.header-actions {
  display: flex;
  gap: var(--spacing-2);
  align-items: center;
  flex-shrink: 0;
}

.btn-action-secondary {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  background-color: var(--bg-card);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background-color var(--duration-200);
}

.btn-action-secondary:hover:not(:disabled) {
  background-color: var(--bg-hover);
}

.btn-action-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3) var(--spacing-4);
  background-color: var(--color-error-bg);
  border: 1px solid var(--color-error-border, #fecaca);
  border-radius: var(--radius-md);
  color: var(--color-error);
  font-size: var(--text-sm);
}

.error-banner span {
  flex: 1;
}

.btn-dismiss {
  background: none;
  border: none;
  color: currentColor;
  cursor: pointer;
  padding: var(--spacing-0);
  flex-shrink: 0;
}
</style>
