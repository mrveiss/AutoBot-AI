<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  ErrorFeed.vue - Real-time error list with severity colors
  Part of Error Monitoring Dashboard (Issue #579)
-->
<template>
  <div class="error-feed">
    <!-- Feed Header -->
    <div class="feed-header">
      <div class="feed-title">
        <i class="fas fa-stream"></i>
        Recent Errors
        <span v-if="errors.length" class="error-count">({{ errors.length }})</span>
      </div>
      <div class="feed-controls">
        <select v-model="severityFilter" class="severity-select">
          <option value="all">All Severities</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </div>
    </div>

    <!-- Empty State -->
    <EmptyState
      v-if="filteredErrors.length === 0"
      icon="fas fa-check-circle"
      message="No errors to display"
      variant="success"
    />

    <!-- Error List -->
    <div v-else class="error-list">
      <TransitionGroup name="error-item">
        <div
          v-for="error in filteredErrors"
          :key="error.trace_id || error.timestamp"
          class="error-item"
          :class="getSeverityClass(error.severity)"
          @click="$emit('select-error', error)"
        >
          <div class="error-severity-indicator" :class="getSeverityClass(error.severity)">
            <i :class="getSeverityIcon(error.severity)"></i>
          </div>
          <div class="error-content">
            <div class="error-header">
              <span class="error-type">{{ error.error_type || error.category || 'Error' }}</span>
              <span class="error-component" v-if="error.component">
                <i class="fas fa-cube"></i> {{ error.component }}
              </span>
            </div>
            <div class="error-message">{{ truncateMessage(error.message) }}</div>
            <div class="error-meta">
              <span class="error-time">
                <i class="fas fa-clock"></i> {{ formatTime(error.timestamp) }}
              </span>
              <span v-if="error.error_code" class="error-code">
                <i class="fas fa-hashtag"></i> {{ error.error_code }}
              </span>
              <span v-if="error.operation" class="error-operation">
                <i class="fas fa-cog"></i> {{ error.operation }}
              </span>
            </div>
          </div>
          <div class="error-actions">
            <button
              class="action-btn"
              @click.stop="$emit('select-error', error)"
              title="View details"
            >
              <i class="fas fa-eye"></i>
            </button>
          </div>
        </div>
      </TransitionGroup>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import EmptyState from '@/components/ui/EmptyState.vue'

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
}

interface Props {
  errors: ErrorReport[]
}

const props = withDefaults(defineProps<Props>(), {
  errors: () => []
})

defineEmits<{
  'select-error': [error: ErrorReport]
}>()

const severityFilter = ref('all')

const filteredErrors = computed(() => {
  if (severityFilter.value === 'all') {
    return props.errors
  }
  return props.errors.filter(error => {
    const severity = (error.severity || 'medium').toLowerCase()
    return severity === severityFilter.value
  })
})

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

const truncateMessage = (message: string, maxLength = 150): string => {
  if (!message) return 'No message provided'
  if (message.length <= maxLength) return message
  return message.substring(0, maxLength) + '...'
}

const formatTime = (timestamp: string | number): string => {
  if (!timestamp) return 'Unknown'
  const date = new Date(timestamp)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMins / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`

  return date.toLocaleDateString()
}
</script>

<style scoped>
.error-feed {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.feed-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-3) var(--spacing-4);
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
}

.feed-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.feed-title i {
  color: var(--color-primary);
}

.error-count {
  color: var(--text-secondary);
  font-weight: var(--font-normal);
}

.severity-select {
  padding: var(--spacing-1-5) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: var(--text-sm);
  cursor: pointer;
}

.severity-select:focus {
  outline: none;
  border-color: var(--color-primary);
}

.error-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-2);
}

.error-item {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-3);
  padding: var(--spacing-3);
  margin-bottom: var(--spacing-2);
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-200) var(--ease-in-out);
}

.error-item:hover {
  background: var(--bg-secondary);
  border-color: var(--border-strong);
  transform: translateX(2px);
}

.error-severity-indicator {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  flex-shrink: 0;
}

.error-severity-indicator.severity-critical {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.error-severity-indicator.severity-high {
  background: rgba(249, 115, 22, 0.15);
  color: var(--chart-orange);
}

.error-severity-indicator.severity-medium {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.error-severity-indicator.severity-low {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.error-content {
  flex: 1;
  min-width: 0;
}

.error-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-1);
  flex-wrap: wrap;
}

.error-type {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.error-component {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  padding: var(--spacing-0-5) var(--spacing-1-5);
  border-radius: var(--radius-sm);
}

.error-component i {
  margin-right: var(--spacing-1);
}

.error-message {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  line-height: 1.4;
  word-break: break-word;
}

.error-meta {
  display: flex;
  gap: var(--spacing-3);
  margin-top: var(--spacing-2);
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  flex-wrap: wrap;
}

.error-meta span {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
}

.error-actions {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.action-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  border: none;
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--duration-150) var(--ease-in-out);
}

.action-btn:hover {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

/* Severity border accents */
.error-item.severity-critical {
  border-left: 3px solid var(--color-error);
}

.error-item.severity-high {
  border-left: 3px solid var(--chart-orange);
}

.error-item.severity-medium {
  border-left: 3px solid var(--color-warning);
}

.error-item.severity-low {
  border-left: 3px solid var(--color-info);
}

/* Transition animations */
.error-item-enter-active,
.error-item-leave-active {
  transition: all var(--duration-300) var(--ease-out);
}

.error-item-enter-from {
  opacity: 0;
  transform: translateX(-20px);
}

.error-item-leave-to {
  opacity: 0;
  transform: translateX(20px);
}

.error-item-move {
  transition: transform var(--duration-300) var(--ease-out);
}

/* Responsive */
@media (max-width: 640px) {
  .feed-header {
    flex-direction: column;
    gap: var(--spacing-2);
    align-items: flex-start;
  }

  .error-meta {
    flex-direction: column;
    gap: var(--spacing-1);
  }

  .error-actions {
    display: none;
  }
}
</style>
