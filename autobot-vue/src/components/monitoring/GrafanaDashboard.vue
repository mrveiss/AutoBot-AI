<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  GrafanaDashboard.vue - Grafana Dashboard Embedding Component
  Phase 4: Grafana Integration (Issue #347)
-->
<template>
  <div class="grafana-embed" :class="{ 'fullscreen': isFullscreen }">
    <div v-if="loading" class="loading-overlay">
      <div class="loading-spinner"></div>
      <p>Loading {{ dashboardTitle }}...</p>
    </div>

    <div v-if="error" class="error-overlay">
      <div class="error-icon">⚠️</div>
      <p>{{ error }}</p>
      <button @click="retry" class="retry-btn">Retry</button>
    </div>

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

    <div class="controls" v-if="showControls">
      <select v-model="selectedTimeRange" @change="updateTimeRange" class="time-select">
        <option value="now-15m">Last 15 minutes</option>
        <option value="now-1h">Last 1 hour</option>
        <option value="now-6h">Last 6 hours</option>
        <option value="now-1d">Last 24 hours</option>
        <option value="now-7d">Last 7 days</option>
        <option value="now-30d">Last 30 days</option>
      </select>

      <select v-model="selectedRefresh" @change="updateRefresh" class="refresh-select">
        <option value="5s">Refresh: 5s</option>
        <option value="10s">Refresh: 10s</option>
        <option value="30s">Refresh: 30s</option>
        <option value="1m">Refresh: 1m</option>
        <option value="off">Refresh: Off</option>
      </select>

      <button @click="toggleFullscreen" class="fullscreen-btn" :title="isFullscreen ? 'Exit fullscreen' : 'Fullscreen'">
        {{ isFullscreen ? '⬇️' : '⬆️' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { getConfig } from '@/config/ssot-config'

// Issue #469: Added 'performance' dashboard type for GPU/NPU metrics
// Issue #472: Added new dashboard types for comprehensive monitoring
type DashboardType =
  | 'overview'
  | 'system'
  | 'workflow'
  | 'errors'
  | 'claude'
  | 'github'
  | 'performance'
  | 'api-health'
  | 'multi-machine'
  | 'knowledge-base'
  | 'llm-providers'
  | 'redis'
  | 'websocket'

interface Props {
  dashboard: DashboardType
  timeRange?: string
  theme?: 'light' | 'dark'
  refresh?: string
  width?: string | number
  height?: string | number
  showControls?: boolean
  grafanaUrl?: string
}

const props = withDefaults(defineProps<Props>(), {
  timeRange: 'now-1h',
  theme: 'dark',
  refresh: '5s',
  width: '100%',
  height: 600,
  showControls: true
})

// Get Grafana URL from SSOT config (computed to handle prop override)
const config = getConfig()
const effectiveGrafanaUrl = computed(() => {
  if (props.grafanaUrl) return props.grafanaUrl
  return `${config.httpProtocol}://${config.vm.redis}:${config.port.grafana}`
})

const emit = defineEmits<{
  (e: 'load'): void
  (e: 'error', error: string): void
  (e: 'timeRangeChange', range: string): void
  (e: 'refreshChange', interval: string): void
}>()

// Dashboard ID mappings
// Issue #469: Added performance dashboard for GPU/NPU metrics
// Issue #472: Added new dashboard IDs for comprehensive monitoring
const dashboardIds: Record<DashboardType, string> = {
  overview: 'autobot-overview',
  system: 'autobot-system',
  workflow: 'autobot-workflow',
  errors: 'autobot-errors',
  claude: 'autobot-claude-api',
  github: 'autobot-github',
  performance: 'autobot-performance',
  'api-health': 'autobot-api-health',
  'multi-machine': 'autobot-multi-machine',
  'knowledge-base': 'autobot-knowledge-base',
  'llm-providers': 'autobot-llm-providers',
  redis: 'autobot-redis',
  websocket: 'autobot-websocket'
}

// Dashboard titles
// Issue #469: Added performance dashboard title
// Issue #472: Added new dashboard titles for comprehensive monitoring
const dashboardTitles: Record<DashboardType, string> = {
  overview: 'AutoBot Overview',
  system: 'System Metrics',
  workflow: 'Workflow Metrics',
  errors: 'Error Metrics',
  claude: 'Claude API Metrics',
  github: 'GitHub Metrics',
  performance: 'GPU/NPU Performance',
  'api-health': 'API Health',
  'multi-machine': 'Multi-Machine Health',
  'knowledge-base': 'Knowledge Base',
  'llm-providers': 'LLM Providers',
  redis: 'Redis Performance',
  websocket: 'WebSocket Metrics'
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
  const dashboardId = dashboardIds[props.dashboard]
  const params = new URLSearchParams({
    orgId: '1',
    theme: props.theme,
    kiosk: 'tv',  // Hide navigation for embed
    from: selectedTimeRange.value,
    to: 'now',
    refresh: selectedRefresh.value
  })
  return `${effectiveGrafanaUrl.value}/d/${dashboardId}?${params}`
})

const iframeStyle = computed(() => ({
  width: typeof props.width === 'number' ? `${props.width}px` : props.width,
  height: typeof props.height === 'number' ? `${props.height}px` : props.height
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

  // Force iframe reload by resetting src
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

// Watch for prop changes
watch(() => props.timeRange, (newRange) => {
  selectedTimeRange.value = newRange
})

watch(() => props.refresh, (newRefresh) => {
  selectedRefresh.value = newRefresh
})

// Lifecycle hooks
onMounted(() => {
  // Set a timeout to show error if iframe doesn't load
  loadTimeout.value = setTimeout(() => {
    if (loading.value) {
      loading.value = false
      error.value = 'Grafana dashboard is taking too long to load. It may be unavailable.'
      emit('error', error.value)
    }
  }, 15000) // 15 second timeout
})

onUnmounted(() => {
  if (loadTimeout.value) {
    clearTimeout(loadTimeout.value)
  }
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.grafana-embed {
  position: relative;
  width: 100%;
  border-radius: var(--radius-lg);
  overflow: hidden;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
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
  background: var(--bg-secondary, #1a1a2e);
  color: var(--text-primary, #fff);
  z-index: 10;
}

.loading-spinner {
  width: 48px;
  height: 48px;
  border: 4px solid var(--border-color, #333);
  border-top-color: var(--primary-color, #4a9eff);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 16px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.error-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.error-overlay p {
  margin-bottom: 16px;
  text-align: center;
  max-width: 400px;
}

.retry-btn {
  padding: 8px 24px;
  background: var(--primary-color, #4a9eff);
  border: none;
  border-radius: 4px;
  color: white;
  cursor: pointer;
  font-size: 14px;
  transition: background 0.2s;
}

.retry-btn:hover {
  background: var(--primary-hover, #3a8eef);
}

.controls {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  background: var(--bg-tertiary, #0f0f1a);
  border-top: 1px solid var(--border-color, #333);
}

.time-select,
.refresh-select {
  padding: 6px 12px;
  background: var(--bg-secondary, #1a1a2e);
  border: 1px solid var(--border-color, #333);
  border-radius: 4px;
  color: var(--text-primary, #fff);
  font-size: 13px;
  cursor: pointer;
}

.time-select:focus,
.refresh-select:focus {
  outline: none;
  border-color: var(--primary-color, #4a9eff);
}

.fullscreen-btn {
  margin-left: auto;
  padding: 6px 12px;
  background: var(--bg-secondary, #1a1a2e);
  border: 1px solid var(--border-color, #333);
  border-radius: 4px;
  color: var(--text-primary, #fff);
  cursor: pointer;
  font-size: 14px;
  transition: background 0.2s;
}

.fullscreen-btn:hover {
  background: var(--bg-tertiary, #0f0f1a);
}

iframe {
  display: block;
  border: none;
}
</style>
