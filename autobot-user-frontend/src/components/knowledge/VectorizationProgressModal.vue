<template>
  <transition name="modal-fade">
    <div v-if="show" class="modal-overlay" @click.self="$emit('close')">
      <div class="modal-container">
        <!-- Header -->
        <div class="modal-header">
          <div class="header-content">
            <i class="fas fa-cubes"></i>
            <h3>Vectorization Progress</h3>
          </div>
          <button class="close-btn" @click="$emit('close')">
            <i class="fas fa-times"></i>
          </button>
        </div>

        <!-- Overall Progress Summary -->
        <div class="progress-summary">
          <div class="summary-stats">
            <div class="stat-item">
              <span class="stat-value">{{ totalDocuments }}</span>
              <span class="stat-label">Total</span>
            </div>
            <div class="stat-item stat-completed">
              <span class="stat-value">{{ completedCount }}</span>
              <span class="stat-label">Completed</span>
            </div>
            <div class="stat-item stat-pending">
              <span class="stat-value">{{ pendingCount }}</span>
              <span class="stat-label">In Progress</span>
            </div>
            <div class="stat-item stat-failed">
              <span class="stat-value">{{ failedCount }}</span>
              <span class="stat-label">Failed</span>
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
            icon="fas fa-inbox"
            message="No documents being vectorized"
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
                    'fas fa-check-circle': doc.status === 'vectorized',
                    'fas fa-spinner fa-spin': doc.status === 'pending',
                    'fas fa-times-circle': doc.status === 'failed',
                    'fas fa-question-circle': doc.status === 'unknown'
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
        <div class="modal-actions">
          <button
            v-if="hasFailedDocuments"
            class="action-btn retry-btn"
            @click="$emit('retry-failed')"
          >
            <i class="fas fa-redo"></i>
            Retry Failed
          </button>
          <button
            v-if="allCompleted"
            class="action-btn close-btn-action"
            @click="$emit('close')"
          >
            <i class="fas fa-check"></i>
            Done
          </button>
          <button
            v-else
            class="action-btn cancel-btn"
            @click="$emit('cancel')"
          >
            <i class="fas fa-stop"></i>
            Cancel
          </button>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import VectorizationStatusBadge from './VectorizationStatusBadge.vue'
import EmptyState from '@/components/ui/EmptyState.vue'

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
/* Modal overlay */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--bg-overlay);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 1rem;
}

.modal-container {
  background: var(--bg-card);
  border-radius: 0.75rem;
  box-shadow: var(--shadow-xl);
  max-width: 700px;
  width: 100%;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
}

/* Header */
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem;
  border-bottom: 2px solid var(--border-default);
}

.header-content {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.header-content i {
  font-size: 1.5rem;
  color: var(--color-primary);
}

.modal-header h3 {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.close-btn {
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  border: none;
  border-radius: 0.375rem;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all 0.2s;
}

.close-btn:hover {
  background: var(--border-default);
  color: var(--text-secondary);
}

/* Progress Summary */
.progress-summary {
  padding: 1.5rem;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
}

.summary-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 1rem;
  background: var(--bg-card);
  border-radius: 0.5rem;
  border: 2px solid var(--border-default);
}

.stat-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-label {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  font-weight: 500;
  margin-top: 0.25rem;
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
  gap: 1rem;
}

.progress-bar {
  flex: 1;
  height: 1.5rem;
  background: var(--border-default);
  border-radius: 0.75rem;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--color-primary), var(--color-primary-hover));
  transition: width 0.3s ease;
  border-radius: 0.75rem;
}

.progress-text {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-secondary);
  min-width: 3rem;
  text-align: right;
}

/* Document List */
.document-list {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
  max-height: 400px;
}

.document-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem;
  margin-bottom: 0.5rem;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 0.5rem;
  transition: all 0.2s;
}

.document-item:hover {
  background: var(--bg-secondary);
  transform: translateX(4px);
}

.document-info {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex: 1;
  min-width: 0;
}

.status-icon {
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 0.375rem;
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
  font-size: 1rem;
}

.document-details {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.document-name {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.error-message {
  font-size: 0.75rem;
  color: var(--color-error);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Mini progress bar for individual documents */
.document-progress {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-right: 0.75rem;
}

.mini-progress-bar {
  width: 80px;
  height: 0.5rem;
  background: var(--border-default);
  border-radius: 0.25rem;
  overflow: hidden;
}

.mini-progress-fill {
  height: 100%;
  background: var(--color-primary);
  transition: width 0.3s ease;
  border-radius: 0.25rem;
}

.progress-percentage {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-tertiary);
  min-width: 3rem;
}

/* Modal Actions */
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  padding: 1.5rem;
  border-top: 2px solid var(--border-default);
  background: var(--bg-secondary);
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 1.25rem;
  border-radius: 0.5rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  border: none;
  font-size: 0.875rem;
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
  border-radius: 4px;
}

.document-list::-webkit-scrollbar-thumb {
  background: var(--border-light);
  border-radius: 4px;
}

.document-list::-webkit-scrollbar-thumb:hover {
  background: var(--border-secondary);
}

/* Modal animations */
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.3s ease;
}

.modal-fade-enter-active .modal-container,
.modal-fade-leave-active .modal-container {
  transition: transform 0.3s ease, opacity 0.3s ease;
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}

.modal-fade-enter-from .modal-container,
.modal-fade-leave-to .modal-container {
  transform: scale(0.9);
  opacity: 0;
}
</style>
