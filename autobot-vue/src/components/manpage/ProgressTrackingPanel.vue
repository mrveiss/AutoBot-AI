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
        <i :class="websocketConnected ? 'fas fa-plug text-green-500' : 'fas fa-plug text-red-500'"></i>
        <span :class="websocketConnected ? 'text-green-600' : 'text-red-600'">
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
  margin-top: 15px;
}

.progress-item {
  margin-bottom: 15px;
}

.progress-label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-weight: 600;
  color: #2c3e50;
}

.progress-percentage {
  font-size: 0.9em;
  color: #7f8c8d;
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: #ecf0f1;
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  transition: width 0.3s ease;
  border-radius: 4px;
}

.progress-fill.waiting {
  background: #95a5a6;
}

.progress-fill.running {
  background: linear-gradient(90deg, #3498db, #2980b9);
}

.progress-fill.success {
  background: linear-gradient(90deg, #27ae60, #229954);
}

.progress-fill.error {
  background: linear-gradient(90deg, #e74c3c, #c0392b);
}

.progress-fill.task-progress {
  background: linear-gradient(90deg, #9b59b6, #8e44ad);
}

.progress-messages {
  background: #ffffff;
  border: 1px solid #dee2e6;
  border-radius: 4px;
  max-height: 200px;
  overflow-y: auto;
  margin: 15px 0;
  padding: 10px;
}

.progress-message {
  display: flex;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid #f1f3f4;
  font-size: 0.9em;
}

.progress-message:last-child {
  border-bottom: none;
}

.progress-message .timestamp {
  color: #6c757d;
  font-size: 0.8em;
  margin-right: 10px;
  min-width: 70px;
}

.progress-message .message {
  flex: 1;
}

.progress-message i {
  margin-right: 8px;
}

.connection-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  background: #ffffff;
  border: 1px solid #dee2e6;
  border-radius: 4px;
  font-size: 0.9em;
}

.text-green-500 { color: #10b981; }
.text-green-600 { color: #059669; }
.text-red-500 { color: #ef4444; }
.text-red-600 { color: #dc2626; }
</style>
