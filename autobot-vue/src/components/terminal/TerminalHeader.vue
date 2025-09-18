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
.window-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: #2d2d2d;
  padding: 8px 16px;
  border-bottom: 1px solid #333;
  user-select: none;
}

.window-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
}

.terminal-icon {
  font-size: 16px;
}

.window-controls {
  display: flex;
  gap: 8px;
}

.control-button {
  background-color: #444;
  border: 1px solid #666;
  color: #fff;
  padding: 4px 8px;
  border-radius: 3px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s;
}

.control-button:hover:not(:disabled) {
  background-color: #555;
  transform: translateY(-1px);
}

.control-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.control-button.danger:hover:not(:disabled) {
  background-color: #dc3545;
}

/* Emergency control button styles */
.control-button.emergency-kill {
  background-color: #dc3545;
  color: white;
  font-weight: bold;
  border-color: #c82333;
}

.control-button.emergency-kill:hover:not(:disabled) {
  background-color: #c82333;
  border-color: #bd2130;
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(220, 53, 69, 0.3);
}

.control-button.interrupt {
  background-color: #ffc107;
  color: #212529;
  border-color: #e0a800;
}

.control-button.interrupt:hover:not(:disabled) {
  background-color: #e0a800;
  border-color: #d39e00;
}

.control-button.takeover {
  background-color: #17a2b8;
  color: white;
  border-color: #138496;
  font-weight: 600;
}

.control-button.takeover:hover:not(:disabled) {
  background-color: #138496;
  border-color: #0c7084;
}

.control-button.takeover.active {
  background-color: #28a745;
  border-color: #1e7e34;
  animation: pulse-success 2s infinite;
}

.control-button.takeover.active:hover {
  background-color: #218838;
}

@keyframes pulse-success {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(40, 167, 69, 0.4);
  }
  50% {
    box-shadow: 0 0 0 8px rgba(40, 167, 69, 0);
  }
}
</style>