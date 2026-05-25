<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  Operations Panel Component
  Issue #4270 - Wire orphaned component OperationDetail

  Provides a two-pane interface combining OperationsList and OperationDetail
  for viewing and managing long-running operations.
-->
<template>
  <div class="operations-panel">
    <!-- List pane -->
    <div class="operations-pane list-pane">
      <OperationsList
        :operations="operations"
        :total-count="totalCount"
        :loading="loading"
        :selected-id="selectedOperationId"
        :empty-message="emptyMessage"
        :filter="filter"
        @select="handleSelectOperation"
        @cancel="handleCancelOperation"
        @resume="handleResumeOperation"
        @update:filter="handleFilterChange"
        @clear-filter="handleClearFilter"
      />
    </div>

    <!-- Detail pane -->
    <div class="operations-pane detail-pane" v-if="selectedOperation">
      <OperationDetail
        :operation="selectedOperation"
        @close="handleCloseDetail"
        @cancel="handleCancelOperation"
        @resume="handleResumeOperation"
        @refresh="handleRefreshOperation"
      />
    </div>

    <!-- Empty detail pane -->
    <div class="operations-pane detail-pane empty-detail" v-else>
      <div class="empty-placeholder">
        <Icon name="info-circle" />
        <p>{{ $t('operations.panel.selectOperation') }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Operation, OperationsFilter } from '@/types/operations'
import OperationsList from './OperationsList.vue'
import OperationDetail from './OperationDetail.vue'

interface Props {
  operations: Operation[]
  totalCount: number
  loading?: boolean
  emptyMessage?: string
  filter?: OperationsFilter
}

const { t } = useI18n()

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  emptyMessage: undefined,
  filter: () => ({
    status: undefined,
    operation_type: undefined,
    limit: 50
  })
})

const emit = defineEmits<{
  cancel: [operationId: string]
  resume: [operationId: string]
  refresh: [operationId: string]
  'update:filter': [filter: OperationsFilter]
  'clear-filter': []
}>()

const selectedOperationId = ref<string | null>(null)

const selectedOperation = computed(() => {
  if (!selectedOperationId.value) return null
  return props.operations.find(op => op.operation_id === selectedOperationId.value) || null
})

function handleSelectOperation(operation: Operation) {
  selectedOperationId.value = operation.operation_id
}

function handleCloseDetail() {
  selectedOperationId.value = null
}

function handleCancelOperation(operationId: string) {
  emit('cancel', operationId)
}

function handleResumeOperation(operationId: string) {
  emit('resume', operationId)
}

function handleRefreshOperation(operationId: string) {
  emit('refresh', operationId)
}

function handleFilterChange(newFilter: OperationsFilter) {
  emit('update:filter', newFilter)
}

function handleClearFilter() {
  emit('clear-filter')
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.operations-panel {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-4);
  height: 100%;
  min-height: 400px;
}

.operations-pane {
  display: flex;
  flex-direction: column;
  background-color: var(--bg-surface);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-default);
  overflow: hidden;
}

.list-pane {
  min-width: 0;
  padding: var(--spacing-4);
}

.detail-pane {
  min-width: 0;
  padding: var(--spacing-4);
  overflow-y: auto;
}

.empty-detail {
  align-items: center;
  justify-content: center;
}

.empty-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-3);
  padding: var(--spacing-8);
  text-align: center;
  color: var(--text-tertiary);
}

.empty-placeholder i {
  font-size: var(--text-4xl);
  color: var(--text-tertiary);
}

.empty-placeholder p {
  margin: var(--spacing-0);
  font-size: var(--text-sm);
}

/* Responsive: Stack on mobile and tablet */
@media (max-width: 1024px) {
  .operations-panel {
    grid-template-columns: 1fr;
    height: auto;
  }

  .detail-pane {
    max-height: 400px;
  }
}
</style>
