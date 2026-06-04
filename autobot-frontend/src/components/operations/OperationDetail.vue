<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  Operation Detail Component
  Issue #591 - Long-Running Operations Tracker
-->
<template>
  <div class="operation-detail" v-if="operation">
    <!-- Header -->
    <div class="detail-header">
      <div class="header-left">
        <i :class="OPERATION_TYPE_ICONS[operation.operation_type]" class="type-icon"></i>
        <div class="header-info">
          <h3 class="operation-name">{{ operation.name }}</h3>
          <span class="operation-type">{{ OPERATION_TYPE_LABELS[operation.operation_type] }}</span>
        </div>
      </div>
      <button class="close-btn" @click="emit('close')" :title="$t('operations.detail.close')">
        <Icon name="times" />
      </button>
    </div>

    <!-- Status badge -->
    <div class="status-section">
      <span class="status-badge" :class="[STATUS_CONFIG[operation.status].bgClass, STATUS_CONFIG[operation.status].textClass]">
        <i :class="STATUS_CONFIG[operation.status].icon"></i>
        {{ STATUS_CONFIG[operation.status].label }}
      </span>
      <span class="priority-badge" :class="`priority-${operation.priority}`">
        {{ $t('operations.detail.priorityLabel', { priority: PRIORITY_CONFIG[operation.priority].label }) }}
      </span>
    </div>

    <!-- Progress -->
    <div class="progress-section">
      <h4 class="section-title">{{ $t('operations.detail.progressTitle') }}</h4>
      <OperationProgress
        :progress="operation.progress"
        :status="operation.status"
        :processed-items="operation.processed_items"
        :estimated-items="operation.estimated_items"
        :current-step="operation.current_step"
        size="lg"
      />
    </div>

    <!-- Description -->
    <div class="description-section" v-if="operation.description">
      <h4 class="section-title">{{ $t('operations.detail.descriptionTitle') }}</h4>
      <p class="description-text">{{ operation.description }}</p>
    </div>

    <!-- Timing info -->
    <div class="timing-section">
      <h4 class="section-title">{{ $t('operations.detail.timingTitle') }}</h4>
      <div class="timing-grid">
        <div class="timing-item">
          <span class="timing-label">{{ $t('operations.detail.created') }}</span>
          <span class="timing-value">{{ formatDateTime(operation.created_at) }}</span>
        </div>
        <div class="timing-item" v-if="operation.started_at">
          <span class="timing-label">{{ $t('operations.detail.started') }}</span>
          <span class="timing-value">{{ formatDateTime(operation.started_at) }}</span>
        </div>
        <div class="timing-item" v-if="operation.completed_at">
          <span class="timing-label">{{ $t('operations.detail.completed') }}</span>
          <span class="timing-value">{{ formatDateTime(operation.completed_at) }}</span>
        </div>
        <div class="timing-item">
          <span class="timing-label">{{ $t('operations.detail.duration') }}</span>
          <span class="timing-value">{{ formatDuration(operation.started_at, operation.completed_at) }}</span>
        </div>
      </div>
    </div>

    <!-- Error message -->
    <div class="error-section" v-if="operation.error_message">
      <h4 class="section-title error-title">
        <Icon name="exclamation-triangle" />
        {{ $t('operations.detail.errorTitle') }}
      </h4>
      <div class="error-message">{{ operation.error_message }}</div>
    </div>

    <!-- Checkpoints info -->
    <div class="checkpoints-section" v-if="operation.checkpoints_count > 0">
      <h4 class="section-title">{{ $t('operations.detail.checkpointsTitle') }}</h4>
      <div class="checkpoints-info">
        <span class="checkpoints-count">{{ $t('operations.detail.checkpointsSaved', { count: operation.checkpoints_count }) }}</span>
        <span class="can-resume" v-if="operation.can_resume">
          <Icon name="redo" /> {{ $t('operations.detail.canBeResumed') }}
        </span>
      </div>
    </div>

    <!-- Context info (collapsible) -->
    <div class="context-section" v-if="hasContext">
      <button class="context-toggle" @click="showContext = !showContext">
        <Icon :name="showContext ? 'chevron-down' : 'chevron-right'" />
        <h4 class="section-title">{{ $t('operations.detail.contextDetails') }}</h4>
      </button>
      <div class="context-content" v-if="showContext">
        <pre class="context-json">{{ JSON.stringify(operation.context, null, 2) }}</pre>
      </div>
    </div>

    <!-- Actions -->
    <div class="actions-section">
      <button
        class="action-btn cancel-btn"
        v-if="canCancelOp"
        @click="handleCancel"
        :disabled="actionLoading"
      >
        <Icon name="stop-circle" />
        {{ $t('operations.detail.cancelOperation') }}
      </button>
      <button
        class="action-btn resume-btn"
        v-if="canResumeOp"
        @click="handleResume"
        :disabled="actionLoading"
      >
        <Icon name="play-circle" />
        {{ $t('operations.detail.resumeOperation') }}
      </button>
      <button
        class="action-btn refresh-btn"
        @click="handleRefresh"
        :disabled="actionLoading"
      >
        <Icon name="sync-alt" />
        {{ $t('operations.detail.refresh') }}
      </button>
    </div>

    <!-- Operation ID footer -->
    <div class="detail-footer">
      <span class="operation-id">{{ $t('operations.detail.idLabel') }} {{ operation.operation_id }}</span>
      <button class="copy-id-btn" @click="copyId" :title="copied ? $t('operations.detail.copied') : $t('operations.detail.copyId')">
        <Icon :name="copied ? 'check' : 'copy'" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Operation } from '@/types/operations'
import {
  STATUS_CONFIG,
  OPERATION_TYPE_LABELS,
  OPERATION_TYPE_ICONS,
  PRIORITY_CONFIG,
  canCancel,
  canResume
} from '@/types/operations'
import { formatDuration } from '@/utils/formatHelpers'
import { useClipboard } from '@/composables/useClipboard'
import OperationProgress from './OperationProgress.vue'

interface Props {
  operation: Operation
}

const { t } = useI18n()
const props = defineProps<Props>()

const emit = defineEmits<{
  close: []
  cancel: [operationId: string]
  resume: [operationId: string]
  refresh: [operationId: string]
}>()

const showContext = ref(false)
const actionLoading = ref(false)
const { copy, copied } = useClipboard({ copiedDuration: 2000 })

const hasContext = computed(() =>
  props.operation.context && Object.keys(props.operation.context).length > 0
)

const canCancelOp = computed(() => canCancel(props.operation))
const canResumeOp = computed(() => canResume(props.operation))

function formatDateTime(timestamp: string | null): string {
  if (!timestamp) return '-'
  return new Date(timestamp).toLocaleString()
}

async function handleCancel() {
  actionLoading.value = true
  try {
    emit('cancel', props.operation.operation_id)
  } finally {
    actionLoading.value = false
  }
}

async function handleResume() {
  actionLoading.value = true
  try {
    emit('resume', props.operation.operation_id)
  } finally {
    actionLoading.value = false
  }
}

function handleRefresh() {
  emit('refresh', props.operation.operation_id)
}

async function copyId() {
  await copy(props.operation.operation_id)
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.operation-detail {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-5);
  padding: var(--spacing-6);
  background-color: var(--bg-surface);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-default);
  max-height: 80vh;
  overflow-y: auto;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.header-left {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-3);
}

.type-icon {
  font-size: var(--text-2xl);
  color: var(--color-info);
  margin-top: var(--spacing-0-5);
}

.header-info {
  display: flex;
  flex-direction: column;
}

.operation-name {
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: var(--spacing-0);
}

.operation-type {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.close-btn {
  padding: var(--spacing-2);
  background: none;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  border-radius: var(--radius-sm);
}

.close-btn:hover {
  background-color: var(--bg-tertiary);
  color: var(--text-secondary);
}

.status-section {
  display: flex;
  gap: var(--spacing-3);
  flex-wrap: wrap;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1-5);
  padding: var(--spacing-1-5) var(--spacing-3);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  border-radius: var(--radius-full);
}

.priority-badge {
  display: inline-flex;
  align-items: center;
  padding: var(--spacing-1-5) var(--spacing-3);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  border-radius: var(--radius-full);
  background-color: var(--bg-tertiary);
  color: var(--text-secondary);
}

.priority-high {
  background-color: var(--color-warning-bg);
  color: var(--color-warning-dark, #92400e);
}

.priority-critical {
  background-color: var(--color-error-bg);
  color: var(--color-error-dark, #991b1b);
}

.section-title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-2) var(--spacing-0);
}

.progress-section,
.description-section,
.timing-section,
.checkpoints-section {
  padding-top: var(--spacing-3);
  border-top: 1px solid var(--border-subtle);
}

.description-text {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: var(--spacing-0);
  line-height: 1.5;
}

.timing-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-3);
}

.timing-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-0-5);
}

.timing-label {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.timing-value {
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.error-section {
  padding: var(--spacing-4);
  background-color: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: var(--radius-md);
}

.error-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  color: #991b1b;
}

.error-message {
  font-size: var(--text-sm);
  color: #7f1d1d;
  font-family: monospace;
  white-space: pre-wrap;
  word-break: break-word;
}

.checkpoints-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.can-resume {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
  color: var(--color-success);
}

.context-section {
  border-top: 1px solid var(--border-subtle);
  padding-top: var(--spacing-3);
}

.context-toggle {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  background: none;
  border: none;
  padding: var(--spacing-0);
  cursor: pointer;
  color: var(--text-secondary);
}

.context-toggle:hover {
  color: var(--text-primary);
}

.context-toggle .section-title {
  margin: var(--spacing-0);
}

.context-content {
  margin-top: var(--spacing-3);
}

.context-json {
  font-size: var(--text-xs);
  background-color: var(--code-bg);
  padding: var(--spacing-4);
  border-radius: var(--radius-md);
  overflow-x: auto;
  margin: var(--spacing-0);
}

.actions-section {
  display: flex;
  gap: var(--spacing-3);
  padding-top: var(--spacing-4);
  border-top: 1px solid var(--border-default);
}

.action-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  padding: var(--spacing-2) var(--spacing-4);
  font-size: var(--text-sm);
  font-weight: 500;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-200);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.cancel-btn {
  background-color: #fee2e2;
  color: #991b1b;
  border: 1px solid #fecaca;
}

.cancel-btn:hover:not(:disabled) {
  background-color: #fecaca;
}

.resume-btn {
  background-color: #dcfce7;
  color: #166534;
  border: 1px solid #bbf7d0;
}

.resume-btn:hover:not(:disabled) {
  background-color: #bbf7d0;
}

.refresh-btn {
  background-color: var(--bg-card);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
}

.refresh-btn:hover:not(:disabled) {
  background-color: var(--bg-hover);
}

.detail-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: var(--spacing-3);
  border-top: 1px solid var(--border-subtle);
}

.operation-id {
  font-size: var(--text-xs);
  font-family: monospace;
  color: var(--text-muted);
}

.copy-id-btn {
  padding: var(--spacing-1) var(--spacing-2);
  font-size: var(--text-xs);
  background: none;
  border: 1px solid var(--border-default);
  color: var(--text-muted);
  border-radius: var(--radius-default);
  cursor: pointer;
}

.copy-id-btn:hover {
  background-color: var(--bg-hover);
  color: var(--text-primary);
}

/* Responsive */
@media (max-width: 640px) {
  .timing-grid {
    grid-template-columns: 1fr;
  }

  .actions-section {
    flex-direction: column;
  }

  .action-btn {
    width: 100%;
    justify-content: center;
  }
}
</style>
