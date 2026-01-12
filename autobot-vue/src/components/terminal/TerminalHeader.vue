<template>
  <div class="window-header">
    <div class="window-title">
      <span class="terminal-icon">⬛</span>
      <span data-testid="terminal-title">Terminal - {{ sessionTitle }}</span>
    </div>
    <div class="window-controls">
      <!-- Emergency Kill Button -->
      <button
        class="control-button emergency-kill"
        data-testid="emergency-kill-button"
        @click="$emit('emergency-kill')"
        :disabled="!hasRunningProcesses"
        title="EMERGENCY KILL - Stop all running processes immediately"
      >
        🛑 KILL
      </button>

      <!-- Session Takeover / Pause Automation -->
      <button
        class="control-button takeover"
        @click="$emit('toggle-automation')"
        :class="{ 'active': automationPaused }"
        :disabled="!hasAutomatedWorkflow"
        :title="automationPaused ? 'Resume automated workflow' : 'Pause automation and take manual control'"
      >
        {{ automationPaused ? '▶️ RESUME' : '⏸️ PAUSE' }}
      </button>

      <!-- Interrupt Current Process -->
      <button
        class="control-button interrupt"
        data-testid="interrupt-button"
        @click="$emit('interrupt-process')"
        :disabled="!hasActiveProcess"
        title="Send Ctrl+C to interrupt current process"
      >
        ⚡ INT
      </button>

      <button
        class="control-button"
        data-testid="reconnect-button"
        @click="$emit('reconnect')"
        :disabled="connecting"
        title="Reconnect"
      >
        {{ connecting ? '⟳' : '🔄' }}
      </button>
      <button
        class="control-button"
        data-testid="clear-button"
        @click="$emit('clear-terminal')"
        title="Clear"
      >
        🗑️
      </button>
      <button
        class="control-button danger"
        @click="$emit('close-window')"
        title="Close Window"
      >
        ✕
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Props {
  sessionTitle: string
  hasRunningProcesses: boolean
  automationPaused: boolean
  hasAutomatedWorkflow: boolean
  hasActiveProcess: boolean
  connecting: boolean
}

interface Emits {
  (e: 'emergency-kill'): void
  (e: 'toggle-automation'): void
  (e: 'interrupt-process'): void
  (e: 'reconnect'): void
  (e: 'clear-terminal'): void
  (e: 'close-window'): void
}

defineProps<Props>()
defineEmits<Emits>()
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.window-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: var(--bg-secondary);
  padding: var(--spacing-2) var(--spacing-4);
  border-bottom: 1px solid var(--border-subtle);
  user-select: none;
}

.window-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.terminal-icon {
  font-size: var(--text-base);
}

.window-controls {
  display: flex;
  gap: var(--spacing-2);
}

.control-button {
  background-color: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-on-primary);
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--text-xs);
  transition: all var(--duration-200) var(--ease-in-out);
}

.control-button:hover:not(:disabled) {
  background-color: var(--bg-hover);
  transform: translateY(-1px);
}

.control-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.control-button.danger:hover:not(:disabled) {
  background-color: var(--color-error);
}

/* Emergency control button styles */
.control-button.emergency-kill {
  background-color: var(--color-error);
  color: var(--text-on-error);
  font-weight: var(--font-bold);
  border-color: var(--color-error-hover);
}

.control-button.emergency-kill:hover:not(:disabled) {
  background-color: var(--color-error-hover);
  border-color: var(--color-error-active);
  transform: translateY(-1px);
  box-shadow: var(--shadow-error);
}

.control-button.interrupt {
  background-color: var(--color-warning);
  color: var(--text-primary-dark);
  border-color: var(--color-warning-hover);
}

.control-button.interrupt:hover:not(:disabled) {
  background-color: var(--color-warning-hover);
  border-color: var(--color-warning-active);
}

.control-button.takeover {
  background-color: var(--color-info);
  color: var(--text-on-primary);
  border-color: var(--color-info-hover);
  font-weight: var(--font-semibold);
}

.control-button.takeover:hover:not(:disabled) {
  background-color: var(--color-info-hover);
  border-color: var(--color-info-active);
}

.control-button.takeover.active {
  background-color: var(--color-success);
  border-color: var(--color-success-hover);
  animation: pulse-success 2s infinite;
}

.control-button.takeover.active:hover {
  background-color: var(--color-success-hover);
}

@keyframes pulse-success {
  0%, 100% {
    box-shadow: 0 0 0 0 var(--color-success-bg);
  }
  50% {
    box-shadow: 0 0 0 8px transparent;
  }
}
</style>