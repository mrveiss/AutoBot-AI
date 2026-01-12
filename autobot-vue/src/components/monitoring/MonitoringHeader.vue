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
/* Issue #704: Migrated to CSS design tokens */
.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-8);
  background: var(--bg-surface);
  padding: var(--spacing-5);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
}

.header-title h1 {
  margin: 0;
  color: var(--text-primary);
  font-size: var(--text-2xl);
}

.header-title .subtitle {
  margin: var(--spacing-1) 0 0 0;
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.monitoring-controls {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
}

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: var(--radius-full);
}

.status-dot.connected {
  background: var(--color-success);
  box-shadow: 0 0 8px var(--color-success-bg-transparent);
}

.status-dot.connecting {
  background: var(--color-warning);
  animation: pulse 1s infinite;
}

.status-dot.disconnected {
  background: var(--color-error);
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
