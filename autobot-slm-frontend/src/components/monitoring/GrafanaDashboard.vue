<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * GrafanaDashboard.vue - Grafana Dashboard Embedding Component for SLM Admin
 *
 * Embeds Grafana dashboards via iframe for detailed metric visualization.
 */

import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { getGrafanaUrl } from '@/config/ssot-config'

type DashboardType =
  | 'overview'
  | 'system'
  | 'performance'
  | 'nodes'
  | 'redis'
  | 'api-health'

interface Props {
  dashboard: DashboardType
  timeRange?: string
  theme?: 'light' | 'dark'
  refresh?: string
  width?: string | number
  height?: string | number
  showControls?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  timeRange: 'now-1h',
  theme: 'light',
  refresh: '5s',
  width: '100%',
  height: 600,
  showControls: true,
})

const emit = defineEmits<{
  (e: 'load'): void
  (e: 'error', error: string): void
  (e: 'timeRangeChange', range: string): void
  (e: 'refreshChange', interval: string): void
}>()

// Dashboard ID mappings
const dashboardIds: Record<DashboardType, string> = {
  overview: 'autobot-overview',
  system: 'autobot-system',
  performance: 'autobot-performance',
  nodes: 'autobot-multi-machine',
  redis: 'autobot-redis',
  'api-health': 'autobot-api-health',
}

const dashboardTitles: Record<DashboardType, string> = {
  overview: 'AutoBot Overview',
  system: 'System Metrics',
  performance: 'GPU/NPU Performance',
  nodes: 'Node Metrics',
  redis: 'Redis Performance',
  'api-health': 'API Health',
}

// State
const iframe = ref<HTMLIFrameElement | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
const isFullscreen = ref(false)
const selectedTimeRange = ref(props.timeRange)
const selectedRefresh = ref(props.refresh)
const loadTimeout = ref<ReturnType<typeof setTimeout> | null>(null)

// Computed properties
const dashboardTitle = computed(() => dashboardTitles[props.dashboard])

const dashboardUrl = computed(() => {
  const baseUrl = getGrafanaUrl()
  const dashboardId = dashboardIds[props.dashboard]
  const params = new URLSearchParams({
    orgId: '1',
    theme: props.theme,
    kiosk: 'tv',
    from: selectedTimeRange.value,
    to: 'now',
    refresh: selectedRefresh.value,
  })
  return `${baseUrl}/d/${dashboardId}?${params}`
})

const iframeStyle = computed(() => ({
  width: typeof props.width === 'number' ? `${props.width}px` : props.width,
  height: typeof props.height === 'number' ? `${props.height}px` : props.height,
}))

// Methods
function onIframeLoad() {
  loading.value = false
  error.value = null
  if (loadTimeout.value) {
    clearTimeout(loadTimeout.value)
    loadTimeout.value = null
  }
  emit('load')
}

function onIframeError() {
  loading.value = false
  error.value = 'Failed to load Grafana dashboard. Please check if Grafana is running.'
  emit('error', error.value)
}

function retry() {
  loading.value = true
  error.value = null
  if (iframe.value) {
    const currentSrc = iframe.value.src
    iframe.value.src = ''
    setTimeout(() => {
      if (iframe.value) {
        iframe.value.src = currentSrc
      }
    }, 100)
  }
}

function updateTimeRange() {
  emit('timeRangeChange', selectedTimeRange.value)
}

function updateRefresh() {
  emit('refreshChange', selectedRefresh.value)
}

function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
}

watch(() => props.timeRange, (newRange) => {
  selectedTimeRange.value = newRange
})

watch(() => props.refresh, (newRefresh) => {
  selectedRefresh.value = newRefresh
})

onMounted(() => {
  loadTimeout.value = setTimeout(() => {
    if (loading.value) {
      loading.value = false
      error.value = 'Grafana dashboard is taking too long to load. It may be unavailable.'
      emit('error', error.value)
    }
  }, 15000)
})

onUnmounted(() => {
  if (loadTimeout.value) {
    clearTimeout(loadTimeout.value)
  }
})
</script>

<template>
  <div class="grafana-embed" :class="{ 'fullscreen': isFullscreen }">
    <!-- Loading State -->
    <div v-if="loading" class="loading-overlay">
      <div class="loading-spinner"></div>
      <p class="text-sm text-gray-600 mt-2">Loading {{ dashboardTitle }}...</p>
    </div>

    <!-- Error State -->
    <div v-if="error" class="error-overlay">
      <div class="text-4xl mb-4">⚠️</div>
      <p class="text-gray-700 mb-4">{{ error }}</p>
      <button @click="retry" class="btn btn-primary">
        Retry
      </button>
    </div>

    <!-- Iframe -->
    <iframe
      v-show="!loading && !error"
      ref="iframe"
      :src="dashboardUrl"
      frameborder="0"
      :width="width"
      :height="height"
      @load="onIframeLoad"
      @error="onIframeError"
      :style="iframeStyle"
    />

    <!-- Controls -->
    <div class="controls" v-if="showControls && !loading && !error">
      <select v-model="selectedTimeRange" @change="updateTimeRange" class="select-sm">
        <option value="now-15m">Last 15 minutes</option>
        <option value="now-1h">Last 1 hour</option>
        <option value="now-6h">Last 6 hours</option>
        <option value="now-1d">Last 24 hours</option>
        <option value="now-7d">Last 7 days</option>
      </select>

      <select v-model="selectedRefresh" @change="updateRefresh" class="select-sm">
        <option value="5s">Refresh: 5s</option>
        <option value="10s">Refresh: 10s</option>
        <option value="30s">Refresh: 30s</option>
        <option value="1m">Refresh: 1m</option>
        <option value="off">Refresh: Off</option>
      </select>

      <button
        @click="toggleFullscreen"
        class="btn-icon"
        :title="isFullscreen ? 'Exit fullscreen' : 'Fullscreen'"
      >
        {{ isFullscreen ? '⬇️' : '⬆️' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.grafana-embed {
  position: relative;
  width: 100%;
  border-radius: 0.5rem;
  overflow: hidden;
  background: #f3f4f6;
  border: 1px solid #e5e7eb;
}

.grafana-embed.fullscreen {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 9999;
  border-radius: 0;
}

.grafana-embed.fullscreen iframe {
  height: calc(100vh - 50px) !important;
}

.loading-overlay,
.error-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: #f9fafb;
  z-index: 10;
}

.loading-spinner {
  width: 48px;
  height: 48px;
  border: 4px solid #e5e7eb;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.controls {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  background: #f9fafb;
  border-top: 1px solid #e5e7eb;
}

.select-sm {
  padding: 6px 12px;
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
}

.select-sm:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
}

.btn-icon {
  margin-left: auto;
  padding: 6px 12px;
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: background 0.2s;
}

.btn-icon:hover {
  background: #f3f4f6;
}

.btn {
  @apply px-4 py-2 rounded-lg font-medium transition-colors;
}

.btn-primary {
  @apply bg-blue-600 text-white hover:bg-blue-700;
}

iframe {
  display: block;
  border: none;
}
</style>
