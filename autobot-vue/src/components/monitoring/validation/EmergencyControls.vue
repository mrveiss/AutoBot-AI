<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  EmergencyControls.vue - Emergency Stop Controls with Double Confirmation
  Critical system control requiring explicit user confirmation (Issue #581)
-->
<template>
  <BasePanel variant="bordered" size="medium" class="emergency-panel">
    <template #header>
      <div class="panel-header-content">
        <h2><i class="fas fa-exclamation-triangle"></i> Emergency Controls</h2>
      </div>
    </template>

    <div class="emergency-controls">
      <!-- System Status -->
      <div class="system-status">
        <div class="status-indicator" :class="systemStatus.validation_system">
          <i :class="getStatusIcon()"></i>
          <span>{{ formatStatus() }}</span>
        </div>
        <div class="status-timestamp" v-if="systemStatus.timestamp">
          {{ formatTimestamp(systemStatus.timestamp) }}
        </div>
      </div>

      <!-- Warning Notice -->
      <div class="warning-notice">
        <i class="fas fa-shield-alt"></i>
        <div class="notice-content">
          <strong>Emergency Stop</strong>
          <p>Immediately halts all running processes and puts the system into safe mode. This action requires double confirmation.</p>
        </div>
      </div>

      <!-- Emergency Stop Button -->
      <button
        v-if="!showConfirmation"
        class="emergency-btn"
        @click="initiateEmergencyStop"
      >
        <i class="fas fa-power-off"></i>
        Emergency Stop
      </button>

      <!-- First Confirmation -->
      <div v-if="showConfirmation && !showFinalConfirmation" class="confirmation-stage">
        <div class="confirmation-warning">
          <i class="fas fa-exclamation-circle"></i>
          <p>Are you sure you want to trigger an emergency stop?</p>
          <p class="warning-detail">This will halt all running processes immediately.</p>
        </div>
        <div class="confirmation-actions">
          <button class="cancel-btn" @click="cancelEmergencyStop">
            <i class="fas fa-times"></i>
            Cancel
          </button>
          <button class="confirm-btn" @click="showFinalConfirmation = true">
            <i class="fas fa-check"></i>
            Confirm
          </button>
        </div>
        <div class="countdown" v-if="countdown > 0">
          Auto-cancel in {{ countdown }}s
        </div>
      </div>

      <!-- Final Confirmation -->
      <div v-if="showFinalConfirmation" class="final-confirmation">
        <div class="final-warning">
          <i class="fas fa-skull-crossbones"></i>
          <p><strong>FINAL CONFIRMATION</strong></p>
          <p>Type "STOP" to confirm emergency shutdown:</p>
        </div>
        <input
          ref="confirmInput"
          v-model="confirmText"
          type="text"
          class="confirm-input"
          placeholder="Type STOP"
          @keyup.enter="executeEmergencyStop"
        >
        <div class="final-actions">
          <button class="cancel-btn" @click="cancelEmergencyStop">
            <i class="fas fa-times"></i>
            Cancel
          </button>
          <button
            class="execute-btn"
            @click="executeEmergencyStop"
            :disabled="confirmText.toUpperCase() !== 'STOP'"
          >
            <i class="fas fa-power-off"></i>
            Execute Stop
          </button>
        </div>
        <div class="countdown" v-if="countdown > 0">
          Auto-cancel in {{ countdown }}s
        </div>
      </div>

      <!-- Executing State -->
      <div v-if="executing" class="executing-state">
        <i class="fas fa-spinner fa-spin"></i>
        <p>Executing emergency stop...</p>
      </div>
    </div>
  </BasePanel>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, watch, nextTick, onUnmounted } from 'vue'
import BasePanel from '@/components/base/BasePanel.vue'

interface SystemStatus {
  validation_system: string
  available_validations: string[]
  last_validation: string | null
  system_health: string
  timestamp: string
}

interface Props {
  systemStatus: SystemStatus
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'emergency-stop'): void
}>()

// State
const showConfirmation = ref(false)
const showFinalConfirmation = ref(false)
const confirmText = ref('')
const executing = ref(false)
const countdown = ref(0)
const confirmInput = ref<HTMLInputElement | null>(null)
let countdownTimer: ReturnType<typeof setInterval> | null = null

// Methods
const getStatusIcon = (): string => {
  const status = props.systemStatus.validation_system
  if (status === 'operational') return 'fas fa-check-circle'
  if (status === 'degraded') return 'fas fa-exclamation-triangle'
  if (status === 'stopped') return 'fas fa-stop-circle'
  return 'fas fa-question-circle'
}

const formatStatus = (): string => {
  const status = props.systemStatus.validation_system
  return status.charAt(0).toUpperCase() + status.slice(1)
}

const formatTimestamp = (timestamp: string): string => {
  if (!timestamp) return ''
  try {
    return new Date(timestamp).toLocaleTimeString()
  } catch {
    return timestamp
  }
}

const initiateEmergencyStop = () => {
  showConfirmation.value = true
  startCountdown()
}

const cancelEmergencyStop = () => {
  showConfirmation.value = false
  showFinalConfirmation.value = false
  confirmText.value = ''
  stopCountdown()
}

const executeEmergencyStop = () => {
  if (confirmText.value.toUpperCase() !== 'STOP') return

  executing.value = true
  stopCountdown()

  // Emit the emergency stop event
  emit('emergency-stop')

  // Reset state after a delay
  setTimeout(() => {
    executing.value = false
    cancelEmergencyStop()
  }, 3000)
}

const startCountdown = () => {
  countdown.value = 30
  stopCountdown()
  countdownTimer = setInterval(() => {
    countdown.value--
    if (countdown.value <= 0) {
      cancelEmergencyStop()
    }
  }, 1000)
}

const stopCountdown = () => {
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }
  countdown.value = 0
}

// Focus input when final confirmation shows
watch(showFinalConfirmation, async (newVal) => {
  if (newVal) {
    await nextTick()
    confirmInput.value?.focus()
  }
})

onUnmounted(() => {
  stopCountdown()
})
</script>

<style scoped>
.emergency-panel :deep(.panel-content) {
  background: linear-gradient(135deg, rgba(239, 68, 68, 0.05) 0%, rgba(239, 68, 68, 0.02) 100%);
}

.panel-header-content {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  width: 100%;
}

.panel-header-content h2 {
  margin: 0;
  font-size: var(--text-lg);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.panel-header-content h2 i {
  color: var(--color-error);
}

/* Emergency Controls Container */
.emergency-controls {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

/* System Status */
.system-status {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-weight: var(--font-semibold);
}

.status-indicator.operational {
  color: var(--color-success);
}

.status-indicator.degraded {
  color: var(--color-warning);
}

.status-indicator.stopped,
.status-indicator.unknown {
  color: var(--text-tertiary);
}

.status-timestamp {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

/* Warning Notice */
.warning-notice {
  display: flex;
  gap: var(--spacing-3);
  padding: var(--spacing-3);
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning);
  border-radius: var(--radius-md);
}

.warning-notice i {
  font-size: var(--text-xl);
  color: var(--color-warning);
  flex-shrink: 0;
}

.notice-content {
  flex: 1;
}

.notice-content strong {
  display: block;
  color: var(--color-warning);
  margin-bottom: var(--spacing-1);
}

.notice-content p {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

/* Emergency Button */
.emergency-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  padding: var(--spacing-4);
  background: var(--color-error);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--text-lg);
  font-weight: var(--font-bold);
  cursor: pointer;
  transition: all var(--duration-150) var(--ease-in-out);
}

.emergency-btn:hover {
  background: var(--color-error-dark);
  transform: scale(1.02);
}

.emergency-btn:active {
  transform: scale(0.98);
}

/* Confirmation Stages */
.confirmation-stage,
.final-confirmation {
  padding: var(--spacing-4);
  background: var(--color-error-bg);
  border: 2px solid var(--color-error);
  border-radius: var(--radius-md);
  animation: fadeIn var(--duration-200) var(--ease-in-out);
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.confirmation-warning,
.final-warning {
  text-align: center;
  margin-bottom: var(--spacing-4);
}

.confirmation-warning i,
.final-warning i {
  font-size: var(--text-3xl);
  color: var(--color-error);
  margin-bottom: var(--spacing-2);
  display: block;
}

.confirmation-warning p,
.final-warning p {
  margin: var(--spacing-1) 0;
  color: var(--text-primary);
}

.warning-detail {
  font-size: var(--text-sm);
  color: var(--text-secondary) !important;
}

/* Confirmation Actions */
.confirmation-actions,
.final-actions {
  display: flex;
  gap: var(--spacing-3);
  justify-content: center;
}

.cancel-btn,
.confirm-btn,
.execute-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  border-radius: var(--radius-md);
  font-weight: var(--font-semibold);
  cursor: pointer;
  transition: all var(--duration-150) var(--ease-in-out);
}

.cancel-btn {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
}

.cancel-btn:hover {
  background: var(--bg-hover);
}

.confirm-btn {
  background: var(--color-warning);
  color: white;
  border: none;
}

.confirm-btn:hover {
  background: var(--color-warning-dark);
}

.execute-btn {
  background: var(--color-error);
  color: white;
  border: none;
}

.execute-btn:hover:not(:disabled) {
  background: var(--color-error-dark);
}

.execute-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Confirm Input */
.confirm-input {
  width: 100%;
  padding: var(--spacing-3);
  margin-bottom: var(--spacing-4);
  border: 2px solid var(--color-error);
  border-radius: var(--radius-md);
  font-size: var(--text-lg);
  text-align: center;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  background: var(--bg-surface);
  color: var(--text-primary);
}

.confirm-input:focus {
  outline: none;
  border-color: var(--color-error-dark);
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.2);
}

/* Countdown */
.countdown {
  text-align: center;
  margin-top: var(--spacing-3);
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

/* Executing State */
.executing-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-8);
  background: var(--color-error-bg);
  border: 2px solid var(--color-error);
  border-radius: var(--radius-md);
}

.executing-state i {
  font-size: var(--text-3xl);
  color: var(--color-error);
  margin-bottom: var(--spacing-3);
}

.executing-state p {
  margin: 0;
  font-weight: var(--font-semibold);
  color: var(--color-error);
}
</style>
