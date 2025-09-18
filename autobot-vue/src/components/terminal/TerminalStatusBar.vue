<template>
  <div class="terminal-status-bar">
    <div class="status-left">
      <div class="connection-status" :class="connectionStatus">
        <div class="status-dot"></div>
        <span>{{ connectionStatusText }}</span>
      </div>
      <div class="session-info">
        <span>Session: {{ sessionId ? sessionId.slice(0, 8) + '...' : 'unknown' }}</span>
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
.terminal-status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: #1e1e1e;
  padding: 4px 16px;
  border-bottom: 1px solid #333;
  font-size: 11px;
  color: #888;
}

.status-left, .status-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.connection-status {
  display: flex;
  align-items: center;
  gap: 6px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #dc3545;
}

.connection-status.connected .status-dot {
  background-color: #28a745;
}

.connection-status.connecting .status-dot {
  background-color: #ffc107;
  animation: pulse 1s infinite;
}

.connection-status.error .status-dot {
  background-color: #dc3545;
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