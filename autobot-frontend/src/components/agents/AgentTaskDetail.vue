<template>
  <div class="agent-task-detail">
    <div class="task-header">
      <h3 class="task-description">{{ task.description }}</h3>
      <div class="task-status-badges">
        <!-- Abstention Badge -->
        <AgentAbstentionBadge
          v-if="task.abstained || task.status === 'abstained'"
          :task="task"
        />
        <!-- Status Badge -->
        <div class="status-badge" :class="statusClass">
          <Icon :name="statusIcon" />
          <span>{{ statusLabel }}</span>
        </div>
      </div>
    </div>

    <div class="task-metadata">
      <div class="metadata-row">
        <span class="metadata-label">Task ID:</span>
        <span class="metadata-value">{{ task.id }}</span>
      </div>
      <div class="metadata-row">
        <span class="metadata-label">Priority:</span>
        <span class="metadata-value">{{ task.priority }}</span>
      </div>
      <div class="metadata-row">
        <span class="metadata-label">Created:</span>
        <span class="metadata-value">{{ formatDate(task.created_at) }}</span>
      </div>
      <div v-if="task.completed_at" class="metadata-row">
        <span class="metadata-label">Completed:</span>
        <span class="metadata-value">{{ formatDate(task.completed_at) }}</span>
      </div>
      <div v-if="task.actual_duration" class="metadata-row">
        <span class="metadata-label">Duration:</span>
        <span class="metadata-value">{{ formatDuration(task.actual_duration) }}</span>
      </div>
    </div>

    <!-- Live Steering Affordance (#10543): visible only while task is running -->
    <div v-if="task.status === 'running'" class="steering-section">
      <div class="section-header">
        <Icon name="edit" />
        <h4>Steer Agent</h4>
      </div>
      <div class="steering-form">
        <textarea
          v-model="steeringText"
          class="steering-input"
          placeholder="Type guidance to redirect the agent (e.g. 'skip that file, focus on the tests')"
          rows="2"
          :disabled="steeringSent"
        />
        <button
          class="steering-btn"
          :disabled="!steeringText.trim() || steeringSent"
          @click="sendSteering"
        >
          {{ steeringSent ? 'Guidance sent' : 'Send guidance' }}
        </button>
      </div>
      <p v-if="steeringAck" class="steering-ack">{{ steeringAck }}</p>
    </div>

    <!-- Abstention Reason Section (GH#6626) -->
    <div v-if="task.abstained && task.abstention_reason" class="abstention-section">
      <div class="section-header">
        <Icon name="info-circle" />
        <h4>Why the Agent Abstained</h4>
      </div>
      <div class="abstention-explanation">
        <p class="explanation-text">
          The agent could not confidently complete this task and chose to abstain
          rather than provide a potentially incorrect result.
        </p>
        <div class="abstention-reason">
          <strong>Reason:</strong>
          <span>{{ task.abstention_reason }}</span>
        </div>
      </div>
    </div>

    <!-- Error Message (for failed tasks) -->
    <div v-if="task.error_message && task.status === 'failed'" class="error-section">
      <div class="section-header">
        <Icon name="exclamation-triangle" />
        <h4>Error Details</h4>
      </div>
      <div class="error-message">{{ task.error_message }}</div>
    </div>

    <!-- Task Result -->
    <div v-if="task.result && Object.keys(task.result).length > 0" class="result-section">
      <div class="section-header">
        <Icon name="file-alt" />
        <h4>Task Result</h4>
      </div>
      <pre class="result-data">{{ JSON.stringify(task.result, null, 2) }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import Icon from '@/components/ui/Icon.vue'
import AgentAbstentionBadge from './AgentAbstentionBadge.vue'
import liveEventService from '@/services/LiveEventService'
import type { AgentTask } from '@/types/models'

/**
 * Agent Task Detail Component (GH#6626)
 *
 * Displays detailed information about an agent task, including abstention
 * status and reason when applicable.
 *
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 */

interface Props {
  task: AgentTask
}

const props = defineProps<Props>()

// Steering state (#10543)
const steeringText = ref('')
const steeringSent = ref(false)
const steeringAck = ref('')

async function sendSteering(): Promise<void> {
  const guidance = steeringText.value.trim()
  if (!guidance || !props.task.id) return
  try {
    await liveEventService.sendSteeringMessage({ task_id: props.task.id, guidance })
    steeringSent.value = true
    steeringAck.value = 'Agent will absorb your guidance on the next iteration.'
    steeringText.value = ''
    setTimeout(() => {
      steeringSent.value = false
      steeringAck.value = ''
    }, 4000)
  } catch {
    steeringAck.value = 'Failed to send guidance — check connection.'
  }
}

const statusClass = computed(() => {
  const status = props.task.status
  return {
    'status-completed': status === 'completed',
    'status-failed': status === 'failed',
    'status-abstained': status === 'abstained' || props.task.abstained,
    'status-running': status === 'running',
    'status-pending': status === 'pending',
    'status-cancelled': status === 'cancelled',
  }
})

const statusIcon = computed(() => {
  switch (props.task.status) {
    case 'completed':
      return 'check-circle'
    case 'failed':
      return 'times-circle'
    case 'abstained':
      return 'help-circle'
    case 'running':
      return 'spinner'
    case 'pending':
      return 'clock'
    case 'cancelled':
      return 'ban'
    default:
      return 'question-circle'
  }
})

const statusLabel = computed(() => {
  return props.task.status.charAt(0).toUpperCase() + props.task.status.slice(1)
})

const formatDate = (dateStr: string): string => {
  return new Date(dateStr).toLocaleString()
}

const formatDuration = (ms: number): string => {
  const seconds = Math.floor(ms / 1000)
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`
  const hours = Math.floor(minutes / 60)
  return `${hours}h ${minutes % 60}m`
}
</script>

<style scoped>
.agent-task-detail {
  padding: 1.5rem;
  background: var(--surface-1, oklch(1 0 0));
  border-radius: 0.5rem;
  border: 1px solid var(--border-1, oklch(0.9 0 0));
}

.task-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1.5rem;
  gap: 1rem;
}

.task-description {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-1, oklch(0.2 0 0));
  margin: 0;
  flex: 1;
}

.task-status-badges {
  display: flex;
  gap: 0.5rem;
  flex-shrink: 0;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.75rem;
  border-radius: 0.375rem;
  font-size: 0.875rem;
  font-weight: 500;
}

.status-completed {
  background-color: oklch(0.95 0.03 150);
  color: oklch(0.3 0.12 150);
  border: 1px solid oklch(0.75 0.08 150);
}

.status-failed {
  background-color: oklch(0.95 0.03 25);
  color: oklch(0.4 0.15 25);
  border: 1px solid oklch(0.75 0.12 25);
}

.status-abstained {
  background-color: oklch(0.95 0.03 85);
  color: oklch(0.4 0.12 85);
  border: 1px solid oklch(0.75 0.12 85);
}

.status-running {
  background-color: oklch(0.95 0.03 240);
  color: oklch(0.4 0.12 240);
  border: 1px solid oklch(0.75 0.08 240);
}

.status-pending,
.status-cancelled {
  background-color: oklch(0.95 0 0);
  color: oklch(0.5 0 0);
  border: 1px solid oklch(0.8 0 0);
}

.task-metadata {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
  padding-bottom: 1.5rem;
  border-bottom: 1px solid var(--border-1, oklch(0.9 0 0));
}

.metadata-row {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.metadata-label {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-3, oklch(0.6 0 0));
}

.metadata-value {
  font-size: 0.9375rem;
  color: var(--text-2, oklch(0.3 0 0));
}

.abstention-section,
.error-section,
.result-section {
  margin-top: 1.5rem;
  padding: 1rem;
  border-radius: 0.375rem;
}

.abstention-section {
  background-color: oklch(0.98 0.02 85);
  border: 1px solid oklch(0.85 0.08 85);
}

.error-section {
  background-color: oklch(0.98 0.02 25);
  border: 1px solid oklch(0.85 0.1 25);
}

.result-section {
  background-color: oklch(0.97 0 0);
  border: 1px solid oklch(0.9 0 0);
}

.section-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.section-header h4 {
  font-size: 1rem;
  font-weight: 600;
  margin: 0;
  color: var(--text-1, oklch(0.2 0 0));
}

.abstention-explanation {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.explanation-text {
  margin: 0;
  color: var(--text-2, oklch(0.4 0 0));
  line-height: 1.6;
}

.abstention-reason {
  display: flex;
  gap: 0.5rem;
  padding: 0.75rem;
  background-color: oklch(1 0 0);
  border-radius: 0.25rem;
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
  font-size: 0.875rem;
}

.abstention-reason strong {
  color: var(--text-1, oklch(0.3 0 0));
}

.error-message,
.result-data {
  margin: 0;
  padding: 0.75rem;
  background-color: oklch(1 0 0);
  border-radius: 0.25rem;
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
  font-size: 0.875rem;
  color: var(--text-2, oklch(0.3 0 0));
  overflow-x: auto;
}

/* Steering affordance (#10543) */
.steering-section {
  margin-top: 1.5rem;
  padding: 1rem;
  border-radius: 0.375rem;
  background-color: oklch(0.97 0.01 240);
  border: 1px solid oklch(0.82 0.06 240);
}

.steering-form {
  display: flex;
  gap: 0.5rem;
  align-items: flex-start;
}

.steering-input {
  flex: 1;
  padding: 0.5rem 0.75rem;
  border: 1px solid oklch(0.75 0.06 240);
  border-radius: 0.25rem;
  font-size: 0.875rem;
  font-family: inherit;
  resize: vertical;
  background-color: oklch(1 0 0);
  color: var(--text-1, oklch(0.2 0 0));
}

.steering-input:disabled {
  opacity: 0.6;
}

.steering-btn {
  padding: 0.5rem 1rem;
  border-radius: 0.25rem;
  font-size: 0.875rem;
  font-weight: 500;
  background-color: oklch(0.5 0.12 240);
  color: oklch(1 0 0);
  border: none;
  cursor: pointer;
  white-space: nowrap;
}

.steering-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.steering-ack {
  margin: 0.5rem 0 0;
  font-size: 0.8125rem;
  color: oklch(0.4 0.1 240);
}

/* Dark mode support */
@media (prefers-color-scheme: dark) {
  .agent-task-detail {
    background: oklch(0.2 0 0);
    border-color: oklch(0.3 0 0);
  }

  .task-description {
    color: oklch(0.9 0 0);
  }

  .status-completed {
    background-color: oklch(0.25 0.08 150);
    color: oklch(0.85 0.1 150);
  }

  .status-failed {
    background-color: oklch(0.25 0.08 25);
    color: oklch(0.85 0.12 25);
  }

  .status-abstained {
    background-color: oklch(0.25 0.08 85);
    color: oklch(0.85 0.1 85);
  }

  .abstention-section {
    background-color: oklch(0.18 0.05 85);
    border-color: oklch(0.35 0.1 85);
  }

  .abstention-reason,
  .error-message,
  .result-data {
    background-color: oklch(0.15 0 0);
    color: oklch(0.8 0 0);
  }
}
</style>
