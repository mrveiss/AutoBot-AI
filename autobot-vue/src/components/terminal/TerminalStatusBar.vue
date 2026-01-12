<template>
  <div class="terminal-status-bar">
    <div class="status-left">
      <div class="connection-status" :class="connectionStatus">
        <div class="status-dot"></div>
        <span>{{ connectionStatusText }}</span>
      </div>
      <div class="session-info">
        <span>Session: {{ sessionId || 'unknown' }}</span>
      </div>
      <div class="debug-info" v-if="!canInput">
        <span style="color: orange; font-size: 12px;">
          Debug: Status={{ connectionStatus }}, Connecting={{ connecting }}, CanInput={{ canInput }}
        </span>
      </div>
    </div>
    <div class="status-right">
      <div class="terminal-stats">
        Lines: {{ outputLinesCount }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  connectionStatus: string
  connecting: boolean
  canInput: boolean
  sessionId: string | null
  outputLinesCount: number
}

const props = defineProps<Props>()

const connectionStatusText = computed(() => {
  switch (props.connectionStatus) {
    case 'connected': return 'Connected'
    case 'connecting': return 'Connecting...'
    case 'disconnected': return 'Disconnected'
    case 'error': return 'Error'
    default: return 'Unknown'
  }
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.terminal-status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: var(--bg-tertiary);
  padding: var(--spacing-1) var(--spacing-4);
  border-bottom: 1px solid var(--border-subtle);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.status-left, .status-right {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
}

.connection-status {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: var(--color-error);
}

.connection-status.connected .status-dot {
  background-color: var(--color-success);
}

.connection-status.connecting .status-dot {
  background-color: var(--color-warning);
  animation: pulse 1s infinite;
}

.connection-status.error .status-dot {
  background-color: var(--color-error);
  animation: flash 0.5s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

@keyframes flash {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
</style>