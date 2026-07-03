<template>
  <BaseModal
    :model-value="show"
    :title="$t('knowledge.vectorization.progressTitle')"
    size="md"
    @close="$emit('close')"
  >
    <template #title>
      <span class="header-content">
        <Icon name="cubes" />
        {{ $t('knowledge.vectorization.progressTitle') }}
      </span>
    </template>

    <!-- Overall Progress Summary -->
    <div class="progress-summary">
      <div class="summary-stats">
        <div class="stat-item">
          <span class="stat-value">{{ totalDocuments }}</span>
          <span class="stat-label">{{ $t('knowledge.vectorization.total') }}</span>
        </div>
        <div class="stat-item stat-completed">
          <span class="stat-value">{{ completedCount }}</span>
          <span class="stat-label">{{ $t('knowledge.vectorization.completed') }}</span>
        </div>
        <div class="stat-item stat-pending">
          <span class="stat-value">{{ pendingCount }}</span>
          <span class="stat-label">{{ $t('knowledge.vectorization.inProgress') }}</span>
        </div>
        <div class="stat-item stat-failed">
          <span class="stat-value">{{ failedCount }}</span>
          <span class="stat-label">{{ $t('knowledge.vectorization.failed') }}</span>
        </div>
      </div>

      <!-- Overall progress bar -->
      <div class="overall-progress">
        <div class="progress-bar">
          <div
            class="progress-fill"
            :style="{ width: `${overallProgress}%` }"
          ></div>
        </div>
        <span class="progress-text">{{ Math.round(overallProgress) }}%</span>
      </div>
    </div>

    <!-- Document List -->
    <div class="document-list">
      <EmptyState
        v-if="documentList.length === 0"
        icon="inbox"
        :message="$t('knowledge.vectorization.noDocuments')"
      />

      <div
        v-for="doc in documentList"
        :key="doc.documentId"
        class="document-item"
        :class="`status-${doc.status}`"
      >
        <!-- Document info -->
        <div class="document-info">
          <div class="status-icon">
            <i
              :class="{
                'check-circle': doc.status === 'vectorized',
                'fas fa-spinner fa-spin': doc.status === 'pending',
                'times-circle': doc.status === 'failed',
                'question-circle': doc.status === 'unknown'
              }"
            ></i>
          </div>
          <div class="document-details">
            <span class="document-name">{{ doc.name || doc.documentId }}</span>
            <span v-if="doc.error" class="error-message">{{ doc.error }}</span>
          </div>
        </div>

        <!-- Progress bar for pending documents -->
        <div v-if="doc.status === 'pending' && doc.progress !== undefined" class="document-progress">
          <div class="mini-progress-bar">
            <div
              class="mini-progress-fill"
              :style="{ width: `${doc.progress}%` }"
            ></div>
          </div>
          <span class="progress-percentage">{{ Math.round(doc.progress) }}%</span>
        </div>

        <!-- Status badge -->
        <VectorizationStatusBadge :status="doc.status" :show-label="true" />
      </div>
    </div>

    <!-- Actions -->
    <template #actions>
      <button
        v-if="hasFailedDocuments"
        class="action-btn retry-btn"
        @click="$emit('retry-failed')"
      >
        <Icon name="redo" />
        {{ $t('knowledge.vectorization.retryFailed') }}
      </button>
      <button
        v-if="allCompleted"
        class="action-btn close-btn-action"
        @click="$emit('close')"
      >
        <Icon name="check" />
        {{ $t('knowledge.vectorization.done') }}
      </button>
      <button
        v-else
        class="action-btn cancel-btn"
        @click="$emit('cancel')"
      >
        <Icon name="stop" />
        {{ $t('knowledge.vectorization.cancelButton') }}
      </button>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { computed } from 'vue'
import VectorizationStatusBadge from './VectorizationStatusBadge.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { BaseModal } from '@autobot/ui'

interface DocumentState {
  documentId: string
  name?: string
  status: 'vectorized' | 'pending' | 'failed' | 'unknown'
  progress?: number
  error?: string
  lastUpdated?: Date
}

interface Props {
  show: boolean
  documentStates: Map<string, DocumentState>
}

const props = defineProps<Props>()

defineEmits<{
  'close': []
  'retry-failed': []
  'cancel': []
}>()

// Computed properties
const documentList = computed(() => {
  return Array.from(props.documentStates.values()).sort((a, b) => {
    // Sort by status: pending first, then failed, then completed
    const statusOrder = { pending: 0, failed: 1, vectorized: 2, unknown: 3 }
    return statusOrder[a.status] - statusOrder[b.status]
  })
})

const totalDocuments = computed(() => props.documentStates.size)

const completedCount = computed(() => {
  return documentList.value.filter(d => d.status === 'vectorized').length
})

const pendingCount = computed(() => {
  return documentList.value.filter(d => d.status === 'pending').length
})

const failedCount = computed(() => {
  return documentList.value.filter(d => d.status === 'failed').length
})

const overallProgress = computed(() => {
  if (totalDocuments.value === 0) return 0
  return (completedCount.value / totalDocuments.value) * 100
})

const hasFailedDocuments = computed(() => failedCount.value > 0)

const allCompleted = computed(() => {
  return totalDocuments.value > 0 && completedCount.value === totalDocuments.value
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.header-content {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
}

.header-content i {
  font-size: var(--text-2xl);
  color: var(--color-primary);
}

/* Progress Summary */
.progress-summary {
  margin: calc(-1 * var(--spacing-6)) calc(-1 * var(--spacing-6)) var(--spacing-6);
  padding: var(--spacing-6);
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
}

.summary-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--spacing-4);
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  border: 2px solid var(--border-default);
}

.stat-value {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text-primary);
}

.stat-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  font-weight: 500;
  margin-top: var(--spacing-1);
}

.stat-completed .stat-value {
  color: var(--color-success);
}

.stat-pending .stat-value {
  color: var(--color-warning);
}

.stat-failed .stat-value {
  color: var(--color-error);
}

/* Overall progress bar */
.overall-progress {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
}

.progress-bar {
  flex: 1;
  height: 1.5rem;
  background: var(--border-default);
  border-radius: var(--radius-xl);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--color-primary);
  transition: width var(--duration-300) var(--ease-out);
  border-radius: var(--radius-xl);
}

.progress-text {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-secondary);
  min-width: 3rem;
  text-align: right;
}

/* Document List */
.document-list {
  overflow-y: auto;
  max-height: 400px;
}

.document-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-3);
  margin-bottom: var(--spacing-2);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  transition: all var(--duration-200);
}

.document-item:hover {
  background: var(--bg-secondary);
  transform: translateX(4px);
}

.document-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  flex: 1;
  min-width: 0;
}

.status-icon {
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  flex-shrink: 0;
}

.status-vectorized .status-icon {
  background: var(--color-success-alpha-10);
  color: var(--color-success);
}

.status-pending .status-icon {
  background: var(--color-warning-alpha-10);
  color: var(--color-warning);
}

.status-failed .status-icon {
  background: var(--color-error-alpha-10);
  color: var(--color-error);
}

.status-unknown .status-icon {
  background: var(--text-tertiary-alpha-10);
  color: var(--text-muted);
}

.status-icon i {
  font-size: var(--text-base);
}

.document-details {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.document-name {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.error-message {
  font-size: var(--text-xs);
  color: var(--color-error);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Mini progress bar for individual documents */
.document-progress {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin-right: var(--spacing-3);
}

.mini-progress-bar {
  width: 80px;
  height: 0.5rem;
  background: var(--border-default);
  border-radius: var(--radius-default);
  overflow: hidden;
}

.mini-progress-fill {
  height: 100%;
  background: var(--color-primary);
  transition: width var(--duration-300) var(--ease-out);
  border-radius: var(--radius-default);
}

.progress-percentage {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-tertiary);
  min-width: 3rem;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2-5) var(--spacing-5);
  border-radius: var(--radius-lg);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration-200);
  border: none;
  font-size: var(--text-sm);
}

.retry-btn {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.retry-btn:hover {
  background: var(--color-primary-hover);
  transform: translateY(-1px);
  box-shadow: var(--shadow-primary);
}

.close-btn-action {
  background: var(--color-success);
  color: var(--text-on-primary);
}

.close-btn-action:hover {
  background: var(--color-success-hover);
  transform: translateY(-1px);
  box-shadow: var(--shadow-success);
}

.cancel-btn {
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
  border: 1px solid var(--border-light);
}

.cancel-btn:hover {
  background: var(--border-default);
  color: var(--text-secondary);
}

/* Scrollbar styling */
.document-list::-webkit-scrollbar {
  width: 8px;
}

.document-list::-webkit-scrollbar-track {
  background: var(--bg-tertiary);
  border-radius: var(--radius-default);
}

.document-list::-webkit-scrollbar-thumb {
  background: var(--border-light);
  border-radius: var(--radius-default);
}

.document-list::-webkit-scrollbar-thumb:hover {
  background: var(--border-secondary);
}
</style>
