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
          <div v-if="documentList.length === 0" class="empty-state">
            <i class="fas fa-inbox"></i>
            <p>No documents being vectorized</p>
          </div>

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
/* Modal overlay */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 1rem;
}

.modal-container {
  background: white;
  border-radius: 0.75rem;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
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
  border-bottom: 2px solid #e5e7eb;
}

.header-content {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.header-content i {
  font-size: 1.5rem;
  color: #3b82f6;
}

.modal-header h3 {
  font-size: 1.25rem;
  font-weight: 600;
  color: #1f2937;
  margin: 0;
}

.close-btn {
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f3f4f6;
  border: none;
  border-radius: 0.375rem;
  color: #6b7280;
  cursor: pointer;
  transition: all 0.2s;
}

.close-btn:hover {
  background: #e5e7eb;
  color: #374151;
}

/* Progress Summary */
.progress-summary {
  padding: 1.5rem;
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
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
  background: white;
  border-radius: 0.5rem;
  border: 2px solid #e5e7eb;
}

.stat-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: #1f2937;
}

.stat-label {
  font-size: 0.75rem;
  color: #6b7280;
  font-weight: 500;
  margin-top: 0.25rem;
}

.stat-completed .stat-value {
  color: #10b981;
}

.stat-pending .stat-value {
  color: #fbbf24;
}

.stat-failed .stat-value {
  color: #ef4444;
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
  background: #e5e7eb;
  border-radius: 0.75rem;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #3b82f6, #2563eb);
  transition: width 0.3s ease;
  border-radius: 0.75rem;
}

.progress-text {
  font-size: 0.875rem;
  font-weight: 600;
  color: #374151;
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

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem;
  color: #9ca3af;
}

.empty-state i {
  font-size: 3rem;
  margin-bottom: 1rem;
  opacity: 0.5;
}

.document-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem;
  margin-bottom: 0.5rem;
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  transition: all 0.2s;
}

.document-item:hover {
  background: #f9fafb;
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
  background: rgba(16, 185, 129, 0.1);
  color: #10b981;
}

.status-pending .status-icon {
  background: rgba(251, 191, 36, 0.1);
  color: #fbbf24;
}

.status-failed .status-icon {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.status-unknown .status-icon {
  background: rgba(107, 114, 128, 0.1);
  color: #9ca3af;
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
  color: #374151;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.error-message {
  font-size: 0.75rem;
  color: #dc2626;
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
  background: #e5e7eb;
  border-radius: 0.25rem;
  overflow: hidden;
}

.mini-progress-fill {
  height: 100%;
  background: #3b82f6;
  transition: width 0.3s ease;
  border-radius: 0.25rem;
}

.progress-percentage {
  font-size: 0.75rem;
  font-weight: 600;
  color: #6b7280;
  min-width: 3rem;
}

/* Modal Actions */
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  padding: 1.5rem;
  border-top: 2px solid #e5e7eb;
  background: #f9fafb;
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
  background: #3b82f6;
  color: white;
}

.retry-btn:hover {
  background: #2563eb;
  transform: translateY(-1px);
  box-shadow: 0 4px 6px rgba(59, 130, 246, 0.3);
}

.close-btn-action {
  background: #10b981;
  color: white;
}

.close-btn-action:hover {
  background: #059669;
  transform: translateY(-1px);
  box-shadow: 0 4px 6px rgba(16, 185, 129, 0.3);
}

.cancel-btn {
  background: #f3f4f6;
  color: #6b7280;
  border: 1px solid #d1d5db;
}

.cancel-btn:hover {
  background: #e5e7eb;
  color: #374151;
}

/* Scrollbar styling */
.document-list::-webkit-scrollbar {
  width: 8px;
}

.document-list::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 4px;
}

.document-list::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 4px;
}

.document-list::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
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
