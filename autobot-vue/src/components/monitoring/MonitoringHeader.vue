<template>
  <div class="dashboard-header">
    <div class="header-title">
      <h1>
        <i class="fas fa-tachometer-alt"></i>
        Performance Monitoring
      </h1>
      <p class="subtitle">Real-time GPU/NPU utilization & Multi-modal AI performance</p>
    </div>

    <div class="monitoring-controls">
      <BaseButton
        @click="$emit('toggle-monitoring')"
        :variant="active ? 'danger' : 'success'"
        :disabled="loading"
      >
        <i :class="active ? 'fas fa-stop' : 'fas fa-play'"></i>
        {{ active ? 'Stop' : 'Start' }} Monitoring
      </BaseButton>

      <BaseButton variant="secondary" @click="$emit('refresh')" :loading="loading">
        <i class="fas fa-sync"></i>
        Refresh
      </BaseButton>

      <div class="status-indicator">
        <span :class="['status-dot', connectionStatus]"></span>
        {{ connectionStatusText }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Monitoring Header Component
 *
 * Header with monitoring controls and connection status.
 * Extracted from MonitoringDashboard.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import { computed } from 'vue'
import BaseButton from '@/components/base/BaseButton.vue'

interface Props {
  active: boolean
  loading: boolean
  connectionStatus: 'connected' | 'connecting' | 'disconnected'
}

interface Emits {
  (e: 'toggle-monitoring'): void
  (e: 'refresh'): void
}

const props = defineProps<Props>()
defineEmits<Emits>()

const connectionStatusText = computed(() => {
  switch (props.connectionStatus) {
    case 'connected': return 'Connected'
    case 'connecting': return 'Connecting...'
    default: return 'Disconnected'
  }
})
</script>

<style scoped>
.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 30px;
  background: white;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.header-title h1 {
  margin: 0;
  color: #333;
  font-size: 1.8em;
}

.header-title .subtitle {
  margin: 5px 0 0 0;
  color: #666;
  font-size: 0.9em;
}

.monitoring-controls {
  display: flex;
  align-items: center;
  gap: 15px;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.9em;
}

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.status-dot.connected {
  background: #4caf50;
  box-shadow: 0 0 8px rgba(76, 175, 80, 0.5);
}

.status-dot.connecting {
  background: #ff9800;
  animation: pulse 1s infinite;
}

.status-dot.disconnected {
  background: #f44336;
}

@keyframes pulse {
  0% { opacity: 1; }
  50% { opacity: 0.5; }
  100% { opacity: 1; }
}

@media (max-width: 768px) {
  .dashboard-header {
    flex-direction: column;
    gap: 15px;
    text-align: center;
  }

  .monitoring-controls {
    flex-wrap: wrap;
    justify-content: center;
  }
}
</style>
