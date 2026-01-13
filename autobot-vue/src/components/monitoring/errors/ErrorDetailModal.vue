<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  ErrorDetailModal.vue - Full error details with stack trace
  Part of Error Monitoring Dashboard (Issue #579)
-->
<template>
  <BaseModal
    v-model="isOpen"
    :title="modalTitle"
    size="large"
    @close="handleClose"
  >
    <div v-if="error" class="error-detail">
      <!-- Error Summary -->
      <div class="detail-section summary-section">
        <div class="severity-badge" :class="getSeverityClass(error.severity)">
          <i :class="getSeverityIcon(error.severity)"></i>
          {{ formatSeverity(error.severity) }}
        </div>
        <div class="error-message-full">{{ error.message }}</div>
      </div>

      <!-- Error Metadata -->
      <div class="detail-section">
        <h4 class="section-title">
          <i class="fas fa-info-circle"></i>
          Error Details
        </h4>
        <div class="metadata-grid">
          <div class="metadata-item" v-if="error.trace_id">
            <span class="meta-label">Trace ID</span>
            <span class="meta-value mono">{{ error.trace_id }}</span>
          </div>
          <div class="metadata-item" v-if="error.error_code">
            <span class="meta-label">Error Code</span>
            <span class="meta-value mono">{{ error.error_code }}</span>
          </div>
          <div class="metadata-item" v-if="error.error_type">
            <span class="meta-label">Error Type</span>
            <span class="meta-value">{{ error.error_type }}</span>
          </div>
          <div class="metadata-item" v-if="error.category">
            <span class="meta-label">Category</span>
            <span class="meta-value">{{ formatCategory(error.category) }}</span>
          </div>
          <div class="metadata-item" v-if="error.component">
            <span class="meta-label">Component</span>
            <span class="meta-value mono">{{ error.component }}</span>
          </div>
          <div class="metadata-item" v-if="error.operation">
            <span class="meta-label">Operation</span>
            <span class="meta-value">{{ error.operation }}</span>
          </div>
          <div class="metadata-item" v-if="error.timestamp">
            <span class="meta-label">Timestamp</span>
            <span class="meta-value">{{ formatTimestamp(error.timestamp) }}</span>
          </div>
          <div class="metadata-item" v-if="error.user_id">
            <span class="meta-label">User ID</span>
            <span class="meta-value mono">{{ error.user_id }}</span>
          </div>
        </div>
      </div>

      <!-- Stack Trace -->
      <div class="detail-section" v-if="error.stack_trace">
        <h4 class="section-title">
          <i class="fas fa-layer-group"></i>
          Stack Trace
        </h4>
        <div class="stack-trace-container">
          <button class="copy-btn" @click="copyStackTrace" title="Copy stack trace">
            <i class="fas fa-copy"></i>
          </button>
          <pre class="stack-trace">{{ error.stack_trace }}</pre>
        </div>
      </div>

      <!-- Context Data -->
      <div class="detail-section" v-if="hasContext">
        <h4 class="section-title">
          <i class="fas fa-database"></i>
          Context Data
        </h4>
        <div class="context-container">
          <button class="copy-btn" @click="copyContext" title="Copy context">
            <i class="fas fa-copy"></i>
          </button>
          <pre class="context-data">{{ formatContext(error.context) }}</pre>
        </div>
      </div>

      <!-- Recommendations -->
      <div class="detail-section" v-if="error.recommendations && error.recommendations.length">
        <h4 class="section-title">
          <i class="fas fa-lightbulb"></i>
          Recommendations
        </h4>
        <ul class="recommendations-list">
          <li v-for="(rec, index) in error.recommendations" :key="index">
            {{ rec }}
          </li>
        </ul>
      </div>
    </div>

    <template #actions>
      <button class="btn btn-secondary" @click="handleClose">
        Close
      </button>
      <button
        v-if="error?.trace_id"
        class="btn btn-primary"
        @click="markResolved"
        :disabled="resolving"
      >
        <i v-if="resolving" class="fas fa-spinner fa-spin"></i>
        <i v-else class="fas fa-check"></i>
        Mark Resolved
      </button>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import BaseModal from '@/components/ui/BaseModal.vue'

interface ErrorReport {
  trace_id?: string
  timestamp: string | number
  error_type?: string
  category?: string
  component?: string
  message: string
  severity?: string
  error_code?: string
  operation?: string
  stack_trace?: string
  context?: Record<string, unknown>
  user_id?: string
  recommendations?: string[]
}

interface Props {
  modelValue: boolean
  error: ErrorReport | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'close': []
  'resolve': [traceId: string]
}>()

const resolving = ref(false)

const isOpen = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
})

const modalTitle = computed(() => {
  if (!props.error) return 'Error Details'
  return props.error.error_type || props.error.category || 'Error Details'
})

const hasContext = computed(() => {
  return props.error?.context && Object.keys(props.error.context).length > 0
})

const handleClose = () => {
  emit('update:modelValue', false)
  emit('close')
}

const getSeverityClass = (severity?: string): string => {
  const sev = (severity || 'medium').toLowerCase()
  return `severity-${sev}`
}

const getSeverityIcon = (severity?: string): string => {
  const sev = (severity || 'medium').toLowerCase()
  switch (sev) {
    case 'critical':
      return 'fas fa-skull-crossbones'
    case 'high':
      return 'fas fa-exclamation-triangle'
    case 'medium':
      return 'fas fa-exclamation-circle'
    case 'low':
      return 'fas fa-info-circle'
    default:
      return 'fas fa-bug'
  }
}

const formatSeverity = (severity?: string): string => {
  return (severity || 'medium').toUpperCase()
}

const formatCategory = (category?: string): string => {
  if (!category) return 'Unknown'
  return category.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
}

const formatTimestamp = (timestamp: string | number): string => {
  if (!timestamp) return 'Unknown'
  return new Date(timestamp).toLocaleString()
}

const formatContext = (context?: Record<string, unknown>): string => {
  if (!context) return '{}'
  return JSON.stringify(context, null, 2)
}

const copyStackTrace = async () => {
  if (props.error?.stack_trace) {
    await navigator.clipboard.writeText(props.error.stack_trace)
  }
}

const copyContext = async () => {
  if (props.error?.context) {
    await navigator.clipboard.writeText(formatContext(props.error.context))
  }
}

const markResolved = async () => {
  if (!props.error?.trace_id) return
  resolving.value = true
  try {
    emit('resolve', props.error.trace_id)
  } finally {
    resolving.value = false
  }
}

// Reset resolving state when error changes
watch(() => props.error, () => {
  resolving.value = false
})
</script>

<style scoped>
.error-detail {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-6);
}

.detail-section {
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-default);
}

.summary-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
  align-items: flex-start;
}

.severity-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-1-5) var(--spacing-3);
  border-radius: var(--radius-md);
  font-weight: var(--font-bold);
  font-size: var(--text-sm);
}

.severity-badge.severity-critical {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.severity-badge.severity-high {
  background: rgba(249, 115, 22, 0.15);
  color: var(--chart-orange);
}

.severity-badge.severity-medium {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.severity-badge.severity-low {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.error-message-full {
  font-size: var(--text-lg);
  color: var(--text-primary);
  line-height: 1.5;
  word-break: break-word;
}

.section-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin: 0 0 var(--spacing-4) 0;
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.section-title i {
  color: var(--color-primary);
}

.metadata-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--spacing-3);
}

.metadata-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.meta-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  text-transform: uppercase;
  font-weight: var(--font-medium);
}

.meta-value {
  font-size: var(--text-sm);
  color: var(--text-primary);
  word-break: break-all;
}

.meta-value.mono {
  font-family: var(--font-mono);
  background: var(--bg-tertiary);
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-sm);
}

.stack-trace-container,
.context-container {
  position: relative;
}

.copy-btn {
  position: absolute;
  top: var(--spacing-2);
  right: var(--spacing-2);
  padding: var(--spacing-1-5) var(--spacing-2);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--duration-150) var(--ease-in-out);
  z-index: 1;
}

.copy-btn:hover {
  background: var(--color-primary);
  color: var(--text-on-primary);
  border-color: var(--color-primary);
}

.stack-trace,
.context-data {
  margin: 0;
  padding: var(--spacing-4);
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  line-height: 1.6;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-primary);
  max-height: 300px;
  overflow-y: auto;
}

.recommendations-list {
  margin: 0;
  padding-left: var(--spacing-5);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.recommendations-list li {
  color: var(--text-secondary);
  line-height: 1.5;
}

.recommendations-list li::marker {
  color: var(--color-warning);
}

/* Button styles */
.btn {
  padding: var(--spacing-2) var(--spacing-4);
  border-radius: var(--radius-md);
  font-weight: var(--font-medium);
  font-size: var(--text-sm);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  transition: all var(--duration-150) var(--ease-in-out);
  border: none;
}

.btn-secondary {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
}

.btn-secondary:hover {
  background: var(--bg-hover);
}

.btn-primary {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-primary-dark);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Responsive */
@media (max-width: 640px) {
  .metadata-grid {
    grid-template-columns: 1fr;
  }

  .stack-trace,
  .context-data {
    font-size: var(--text-xs);
    max-height: 200px;
  }
}
</style>
