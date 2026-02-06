<template>
  <BasePanel v-if="show" variant="bordered" size="medium">
    <template #header>
      <h3><i class="fas fa-tasks"></i> Progress Tracking</h3>
      <BaseButton
        size="sm"
        variant="outline"
        @click="$emit('hide')"
      >
        <i class="fas fa-times"></i>
        Hide
      </BaseButton>
    </template>

    <div class="progress-container">
      <!-- Overall Progress -->
      <div class="progress-item">
        <div class="progress-label">
          <span>{{ state.currentTask || 'Waiting...' }}</span>
          <span class="progress-percentage">{{ Math.round(state.overallProgress) }}%</span>
        </div>
        <div class="progress-bar">
          <div
            class="progress-fill"
            :style="{ width: state.overallProgress + '%' }"
            :class="state.status"
          ></div>
        </div>
      </div>

      <!-- Task-specific Progress -->
      <div v-if="state.taskProgress > 0" class="progress-item">
        <div class="progress-label">
          <span>{{ state.taskDetail || 'Processing...' }}</span>
          <span class="progress-percentage">{{ Math.round(state.taskProgress) }}%</span>
        </div>
        <div class="progress-bar">
          <div
            class="progress-fill task-progress"
            :style="{ width: state.taskProgress + '%' }"
          ></div>
        </div>
      </div>

      <!-- Progress Messages -->
      <div class="progress-messages">
        <div
          v-for="(message, index) in recentMessages"
          :key="index"
          class="progress-message"
          :class="message.type"
        >
          <i :class="getMessageIcon(message.type)"></i>
          <span class="timestamp">{{ formatTime(new Date(message.timestamp)) }}</span>
          <span class="message">{{ message.text }}</span>
        </div>
      </div>

      <!-- Connection Status -->
      <div class="connection-status">
        <i :class="websocketConnected ? 'fas fa-plug connected' : 'fas fa-plug disconnected'"></i>
        <span :class="websocketConnected ? 'connected' : 'disconnected'">
          {{ websocketConnected ? 'Connected' : 'Disconnected' }}
        </span>
      </div>
    </div>
  </BasePanel>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Progress Tracking Panel Component
 *
 * Displays real-time progress for long-running operations.
 * Extracted from ManPageManager.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 * Issue #704: Migrated to design tokens for centralized theming
 */

import { computed } from 'vue'
import BasePanel from '@/components/base/BasePanel.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import { useKnowledgeBase } from '@/composables/useKnowledgeBase'

interface ProgressMessage {
  text: string
  type: 'info' | 'success' | 'warning' | 'error'
  timestamp: number
}

interface ProgressState {
  currentTask: string
  taskDetail: string
  overallProgress: number
  taskProgress: number
  status: 'waiting' | 'running' | 'success' | 'error'
  messages: ProgressMessage[]
}

interface Props {
  show: boolean
  state: ProgressState
  websocketConnected?: boolean
}

interface Emits {
  (e: 'hide'): void
}

const props = withDefaults(defineProps<Props>(), {
  websocketConnected: false
})

defineEmits<Emits>()

const { getMessageIcon, formatTime } = useKnowledgeBase()

const recentMessages = computed(() => props.state.messages.slice(-5))
</script>

<style scoped>
.progress-container {
  margin-top: var(--spacing-4);
}

.progress-item {
  margin-bottom: var(--spacing-4);
}

.progress-label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-2);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.progress-percentage {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-default);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  transition: width var(--duration-300) var(--ease-out);
  border-radius: var(--radius-default);
}

.progress-fill.waiting {
  background: var(--text-tertiary);
}

.progress-fill.running {
  background: linear-gradient(90deg, var(--color-info), var(--color-info-hover));
}

.progress-fill.success {
  background: linear-gradient(90deg, var(--color-success), var(--color-success-hover));
}

.progress-fill.error {
  background: linear-gradient(90deg, var(--color-error), var(--color-error-hover));
}

.progress-fill.task-progress {
  background: linear-gradient(90deg, var(--chart-purple), var(--chart-purple-light));
}

.progress-messages {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-default);
  max-height: 200px;
  overflow-y: auto;
  margin: var(--spacing-4) 0;
  padding: var(--spacing-2-5);
}

.progress-message {
  display: flex;
  align-items: center;
  padding: var(--spacing-2) 0;
  border-bottom: 1px solid var(--border-subtle);
  font-size: var(--text-sm);
}

.progress-message:last-child {
  border-bottom: none;
}

.progress-message .timestamp {
  color: var(--text-tertiary);
  font-size: var(--text-xs);
  margin-right: var(--spacing-2-5);
  min-width: 70px;
}

.progress-message .message {
  flex: 1;
}

.progress-message i {
  margin-right: var(--spacing-2);
}

.connection-status {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-default);
  font-size: var(--text-sm);
}

.connection-status .connected {
  color: var(--color-success);
}

.connection-status .disconnected {
  color: var(--color-error);
}
</style>
