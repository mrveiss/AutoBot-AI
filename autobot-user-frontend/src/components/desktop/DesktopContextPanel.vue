<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<template>
  <div class="desktop-context-panel">
    <div class="panel-header">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">Desktop Context</h3>
      <button @click="refresh" :disabled="loading" class="refresh-btn" title="Refresh">
        <svg class="w-4 h-4" :class="{ 'animate-spin': loading }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
      </button>
    </div>

    <div v-if="error" class="error-message">
      {{ error }}
    </div>

    <div v-else-if="context" class="context-sections">
      <!-- System Info -->
      <div class="context-section">
        <h4 class="section-title">System</h4>
        <div class="info-grid">
          <div class="info-item">
            <span class="info-label">CPU Load</span>
            <span class="info-value">{{ context.system.cpu_load_1min || 'N/A' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">Memory</span>
            <span class="info-value">
              {{ context.system.memory_percent }}% ({{ context.system.memory_used_mb }}MB / {{ context.system.memory_total_mb }}MB)
            </span>
          </div>
          <div class="info-item">
            <span class="info-label">Uptime</span>
            <span class="info-value">{{ context.system.uptime || 'N/A' }}</span>
          </div>
        </div>
      </div>

      <!-- Desktop Info -->
      <div class="context-section">
        <h4 class="section-title">Desktop</h4>
        <div class="info-grid">
          <div class="info-item">
            <span class="info-label">Resolution</span>
            <span class="info-value">{{ context.desktop.resolution || 'N/A' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">Active Window</span>
            <span class="info-value text-truncate">{{ context.desktop.active_window || 'None' }}</span>
          </div>
          <div v-if="context.desktop.window_count" class="info-item">
            <span class="info-label">Windows</span>
            <span class="info-value">{{ context.desktop.window_count }}</span>
          </div>
        </div>
      </div>

      <!-- Running Processes -->
      <div v-if="context.processes && context.processes.length > 0" class="context-section">
        <h4 class="section-title">Top Processes (by CPU)</h4>
        <div class="process-list">
          <div v-for="proc in context.processes" :key="proc.pid" class="process-item">
            <div class="process-info">
              <span class="process-pid">PID {{ proc.pid }}</span>
              <span class="process-command">{{ proc.command }}</span>
            </div>
            <div class="process-stats">
              <span class="process-cpu">CPU: {{ proc.cpu }}%</span>
              <span class="process-mem">MEM: {{ proc.mem }}%</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Last Update -->
      <div class="update-time">
        Last updated: {{ formatTime(context.timestamp) }}
      </div>
    </div>

    <div v-else class="loading-state">
      Loading context...
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import ApiClient from '@/api/ApiClient'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('DesktopContextPanel')

interface DesktopContext {
  system: {
    cpu_load_1min?: string
    cpu_load_5min?: string
    cpu_load_15min?: string
    memory_used_mb?: string
    memory_total_mb?: string
    memory_percent?: string
    uptime?: string
  }
  desktop: {
    resolution?: string
    active_window?: string
    window_count?: string
  }
  processes?: Array<{
    pid: string
    cpu: string
    mem: string
    command: string
  }>
  timestamp: string
}

const context = ref<DesktopContext | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
let refreshInterval: number | null = null

async function fetchContext() {
  loading.value = true
  error.value = null

  try {
    const data = await ApiClient.get<DesktopContext>('/vnc/desktop/context')
    context.value = data
  } catch (err: any) {
    logger.error('Failed to fetch desktop context:', err)
    error.value = 'Failed to load desktop context'
  } finally {
    loading.value = false
  }
}

function refresh() {
  fetchContext()
}

function formatTime(timestamp: string): string {
  try {
    const date = new Date(timestamp)
    return date.toLocaleTimeString()
  } catch {
    return timestamp
  }
}

onMounted(() => {
  fetchContext()
  // Auto-refresh every 5 seconds
  refreshInterval = window.setInterval(fetchContext, 5000)
})

onUnmounted(() => {
  if (refreshInterval !== null) {
    clearInterval(refreshInterval)
  }
})
</script>

<style scoped>
.desktop-context-panel {
  @apply bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4;
}

.panel-header {
  @apply flex items-center justify-between mb-4 pb-2 border-b border-gray-200 dark:border-gray-700;
}

.refresh-btn {
  @apply p-1 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 transition-colors;
}

.error-message {
  @apply text-sm text-red-600 dark:text-red-400 p-2 bg-red-50 dark:bg-red-900/20 rounded;
}

.loading-state {
  @apply text-sm text-gray-500 dark:text-gray-400 text-center py-4;
}

.context-sections {
  @apply space-y-4;
}

.context-section {
  @apply space-y-2;
}

.section-title {
  @apply text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide;
}

.info-grid {
  @apply space-y-1.5;
}

.info-item {
  @apply flex items-start justify-between text-xs;
}

.info-label {
  @apply text-gray-600 dark:text-gray-400 font-medium;
}

.info-value {
  @apply text-gray-900 dark:text-gray-100 font-mono text-right;
}

.text-truncate {
  @apply truncate max-w-xs;
}

.process-list {
  @apply space-y-2 max-h-48 overflow-y-auto;
}

.process-item {
  @apply flex items-center justify-between text-xs p-2 bg-gray-50 dark:bg-gray-700/50 rounded;
}

.process-info {
  @apply flex flex-col gap-0.5 flex-1 min-w-0;
}

.process-pid {
  @apply text-gray-500 dark:text-gray-400 font-mono text-[10px];
}

.process-command {
  @apply text-gray-900 dark:text-gray-100 truncate;
}

.process-stats {
  @apply flex gap-2 text-gray-600 dark:text-gray-300 font-mono;
}

.process-cpu, .process-mem {
  @apply text-[10px];
}

.update-time {
  @apply text-[10px] text-gray-500 dark:text-gray-400 text-center mt-2 pt-2 border-t border-gray-200 dark:border-gray-700;
}
</style>
