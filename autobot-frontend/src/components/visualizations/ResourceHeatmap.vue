<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  ResourceHeatmap.vue - Performance heatmap visualization
  Displays resource usage patterns over time in a heatmap format
  Issue #62: Enhanced Visualizations
-->
<template>
  <div class="resource-heatmap">
    <div class="heatmap-header">
      <h3>{{ title }}</h3>
      <div class="header-actions">
        <select v-model="selectedMetric" @change="updateData" class="metric-select">
          <option value="cpu">CPU Usage</option>
          <option value="memory">Memory Usage</option>
          <option value="disk">Disk I/O</option>
          <option value="network">Network I/O</option>
        </select>
        <select v-model="timeRange" @change="fetchData" class="time-select">
          <option value="1h">Last Hour</option>
          <option value="6h">Last 6 Hours</option>
          <option value="24h">Last 24 Hours</option>
          <option value="7d">Last 7 Days</option>
        </select>
        <button @click="fetchData" class="refresh-btn" :disabled="isLoading">
          <i class="fas fa-sync" :class="{ 'fa-spin': isLoading }"></i>
        </button>
      </div>
    </div>

    <div v-if="isLoading" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      <span>Loading heatmap data...</span>
    </div>

    <div v-else-if="error" class="error-state">
      <i class="fas fa-exclamation-triangle"></i>
      <span>{{ error }}</span>
      <button @click="fetchData" class="retry-btn">Retry</button>
    </div>

    <div v-else class="heatmap-container">
      <!-- ApexCharts Heatmap -->
      <apexchart
        ref="chartRef"
        type="heatmap"
        :height="height"
        :options="chartOptions"
        :series="chartSeries"
      />

      <!-- Legend -->
      <div class="heatmap-legend">
        <span class="legend-label">Low</span>
        <div class="legend-gradient"></div>
        <span class="legend-label">High</span>
      </div>

      <!-- Summary Stats -->
      <div class="heatmap-stats">
        <div class="stat-item">
          <span class="stat-label">Peak</span>
          <span class="stat-value peak">{{ peakValue }}%</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">Average</span>
          <span class="stat-value">{{ averageValue }}%</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">Minimum</span>
          <span class="stat-value low">{{ minValue }}%</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import VueApexCharts from 'vue3-apexcharts'
import type { ApexOptions } from 'apexcharts'
import { createLogger } from '@/utils/debugUtils'

const apexchart = VueApexCharts
const logger = createLogger('ResourceHeatmap')

// Props
interface Props {
  title?: string
  height?: number
  refreshInterval?: number
  machine?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: 'Resource Utilization Heatmap',
  height: 350,
  refreshInterval: 60000,
  machine: 'all'
})

// Emit events
const emit = defineEmits<{
  (e: 'cell-click', data: { machine: string; time: string; value: number }): void
}>()

// State
const isLoading = ref(false)
const error = ref<string | null>(null)
const selectedMetric = ref('cpu')
const timeRange = ref('1h')
const chartRef = ref<InstanceType<typeof VueApexCharts> | null>(null)

// Data
const heatmapData = ref<Array<{ name: string; data: Array<{ x: string; y: number }> }>>([])

/**
 * Issue #704: Helper to get CSS custom property values from design tokens
 */
function getCssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

// Computed
const chartSeries = computed(() => heatmapData.value)

const peakValue = computed(() => {
  let max = 0
  heatmapData.value.forEach(series => {
    series.data.forEach(point => {
      if (point.y > max) max = point.y
    })
  })
  return Math.round(max)
})

const averageValue = computed(() => {
  let sum = 0
  let count = 0
  heatmapData.value.forEach(series => {
    series.data.forEach(point => {
      sum += point.y
      count++
    })
  })
  return count > 0 ? Math.round(sum / count) : 0
})

const minValue = computed(() => {
  let min = 100
  heatmapData.value.forEach(series => {
    series.data.forEach(point => {
      if (point.y < min) min = point.y
    })
  })
  return Math.round(min)
})

const chartOptions = computed<ApexOptions>(() => ({
  chart: {
    type: 'heatmap',
    background: 'transparent',
    foreColor: getCssVar('--text-primary'),
    fontFamily: getCssVar('--font-sans'),
    toolbar: {
      show: true,
      tools: {
        download: true,
        selection: false,
        zoom: false,
        zoomin: false,
        zoomout: false,
        pan: false,
        reset: false
      }
    },
    events: {
      dataPointSelection: (_event: MouseEvent, _chartContext: unknown, config: { seriesIndex: number; dataPointIndex: number }) => {
        const series = heatmapData.value[config.seriesIndex]
        const point = series.data[config.dataPointIndex]
        emit('cell-click', {
          machine: series.name,
          time: point.x,
          value: point.y
        })
      }
    }
  },
  dataLabels: {
    enabled: false
  },
  colors: [getCssVar('--chart-blue')],
  plotOptions: {
    heatmap: {
      shadeIntensity: 0.5,
      radius: 2,
      useFillColorAsStroke: false,
      colorScale: {
        ranges: [
          { from: 0, to: 20, color: getCssVar('--color-info-dark'), name: 'Low' },
          { from: 21, to: 40, color: getCssVar('--color-info-hover'), name: 'Moderate' },
          { from: 41, to: 60, color: getCssVar('--chart-blue'), name: 'Medium' },
          { from: 61, to: 80, color: getCssVar('--color-warning'), name: 'High' },
          { from: 81, to: 100, color: getCssVar('--color-error'), name: 'Critical' }
        ]
      }
    }
  },
  stroke: {
    width: 1,
    colors: [getCssVar('--bg-secondary')]
  },
  xaxis: {
    type: 'category',
    labels: {
      style: {
        colors: getCssVar('--text-secondary'),
        fontSize: '11px'
      },
      rotate: -45,
      rotateAlways: false
    },
    axisBorder: {
      show: true,
      color: getCssVar('--border-default')
    }
  },
  yaxis: {
    labels: {
      style: {
        colors: getCssVar('--text-secondary'),
        fontSize: '12px'
      }
    }
  },
  tooltip: {
    enabled: true,
    theme: 'dark',
    custom: ({ seriesIndex, dataPointIndex, w }: {
      seriesIndex: number
      dataPointIndex: number
      w: { config: { series: Array<{ name: string; data: Array<{ x: string; y: number }> }> } }
    }) => {
      const series = w.config.series[seriesIndex]
      const point = series.data[dataPointIndex]
      return `
        <div class="heatmap-tooltip">
          <div class="tooltip-header">${series.name}</div>
          <div class="tooltip-row">
            <span class="tooltip-label">Time:</span>
            <span class="tooltip-value">${point.x}</span>
          </div>
          <div class="tooltip-row">
            <span class="tooltip-label">${getMetricLabel()}:</span>
            <span class="tooltip-value ${getValueClass(point.y)}">${point.y}%</span>
          </div>
        </div>
      `
    }
  },
  grid: {
    show: false
  },
  legend: {
    show: false
  }
}))

// Methods
function getMetricLabel(): string {
  const labels: Record<string, string> = {
    cpu: 'CPU Usage',
    memory: 'Memory Usage',
    disk: 'Disk I/O',
    network: 'Network I/O'
  }
  return labels[selectedMetric.value] || 'Usage'
}

function getValueClass(value: number): string {
  if (value >= 80) return 'critical'
  if (value >= 60) return 'high'
  if (value >= 40) return 'medium'
  return 'low'
}

async function fetchData() {
  isLoading.value = true
  error.value = null

  try {
    // Fetch historical metrics from backend
    const response = await fetch(`/api/monitoring/metrics/history?metric=${selectedMetric.value}&range=${timeRange.value}&machine=${props.machine}`)

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    }

    const data = await response.json()
    processData(data)
  } catch (err) {
    logger.error('Failed to fetch heatmap data:', err)
    error.value = err instanceof Error ? err.message : 'Failed to load data'

    // Generate sample data for demo
    generateSampleData()
  } finally {
    isLoading.value = false
  }
}

function processData(data: { machines: Array<{ name: string; metrics: Array<{ time: string; value: number }> }> }) {
  if (!data.machines || !Array.isArray(data.machines)) {
    generateSampleData()
    return
  }

  heatmapData.value = data.machines.map(machine => ({
    name: machine.name,
    data: machine.metrics.map(m => ({
      x: m.time,
      y: m.value
    }))
  }))
}

function generateSampleData() {
  // Generate realistic sample data for the heatmap
  const machines = ['Main (WSL)', 'Frontend VM', 'NPU Worker', 'Redis VM', 'AI Stack', 'Browser VM']
  const now = new Date()
  const intervals = getTimeIntervals()

  heatmapData.value = machines.map((machine, machineIdx) => ({
    name: machine,
    data: intervals.map((interval, idx) => {
      // Generate realistic patterns
      let baseValue = 30 + Math.random() * 20

      // Add time-based patterns (higher during work hours)
      const hour = new Date(interval).getHours()
      if (hour >= 9 && hour <= 17) {
        baseValue += 20
      }

      // Add machine-specific patterns
      if (machineIdx === 0) baseValue += 10 // Main machine higher
      if (machineIdx === 2) baseValue += Math.sin(idx / 5) * 15 // NPU varies

      // Add some random spikes
      if (Math.random() > 0.9) baseValue += 30

      return {
        x: formatTimeLabel(interval),
        y: Math.min(100, Math.max(0, Math.round(baseValue)))
      }
    })
  }))
}

function getTimeIntervals(): Date[] {
  const intervals: Date[] = []
  const now = new Date()
  let count: number
  let step: number

  switch (timeRange.value) {
    case '1h':
      count = 12
      step = 5 * 60 * 1000 // 5 minutes
      break
    case '6h':
      count = 24
      step = 15 * 60 * 1000 // 15 minutes
      break
    case '24h':
      count = 24
      step = 60 * 60 * 1000 // 1 hour
      break
    case '7d':
      count = 28
      step = 6 * 60 * 60 * 1000 // 6 hours
      break
    default:
      count = 12
      step = 5 * 60 * 1000
  }

  for (let i = count - 1; i >= 0; i--) {
    intervals.push(new Date(now.getTime() - i * step))
  }

  return intervals
}

function formatTimeLabel(date: Date): string {
  switch (timeRange.value) {
    case '1h':
    case '6h':
      return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
    case '24h':
      return date.toLocaleTimeString('en-US', { hour: '2-digit' }) + 'h'
    case '7d':
      return date.toLocaleDateString('en-US', { weekday: 'short' }) + ' ' +
             date.toLocaleTimeString('en-US', { hour: '2-digit' })
    default:
      return date.toLocaleTimeString()
  }
}

function updateData() {
  // Data will be refetched when metric changes
  fetchData()
}

// Lifecycle
let refreshTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  fetchData()

  if (props.refreshInterval > 0) {
    refreshTimer = setInterval(fetchData, props.refreshInterval)
  }
})

// Watch for prop changes
watch(() => props.machine, () => {
  fetchData()
})

// Cleanup
import { onUnmounted } from 'vue'
onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
  }
})

// Expose methods
defineExpose({
  refresh: fetchData
})
</script>

<!-- Issue #704: Migrated to design tokens -->
<style scoped>
.resource-heatmap {
  background: var(--bg-secondary-alpha);
  border-radius: var(--radius-xl);
  padding: var(--spacing-5);
  border: 1px solid var(--border-subtle);
}

.heatmap-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-5);
  padding-bottom: var(--spacing-4);
  border-bottom: 1px solid var(--border-subtle);
}

.heatmap-header h3 {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0;
}

.header-actions {
  display: flex;
  gap: var(--spacing-3);
  align-items: center;
}

.metric-select,
.time-select {
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-tertiary-alpha);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: border-color var(--duration-200);
}

.metric-select:focus,
.time-select:focus {
  outline: none;
  border-color: var(--chart-blue);
}

.refresh-btn {
  padding: var(--spacing-2) var(--spacing-3);
  background: transparent;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--duration-200);
}

.refresh-btn:hover:not(:disabled) {
  background: var(--color-info-bg);
  border-color: var(--chart-blue);
  color: var(--chart-blue);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.loading-state,
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  gap: var(--spacing-3);
  color: var(--text-secondary);
}

.error-state {
  color: var(--color-error-light);
}

.retry-btn {
  margin-top: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--color-info-bg-hover);
  border: 1px solid var(--chart-blue);
  border-radius: var(--radius-md);
  color: var(--chart-blue);
  cursor: pointer;
  transition: background var(--duration-200);
}

.retry-btn:hover {
  background: rgba(59, 130, 246, 0.3);
}

.heatmap-container {
  position: relative;
}

.heatmap-legend {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-3);
  margin-top: var(--spacing-4);
}

.legend-label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.legend-gradient {
  width: 200px;
  height: 12px;
  border-radius: var(--radius-md);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
}

.heatmap-stats {
  display: flex;
  justify-content: center;
  gap: var(--spacing-8);
  margin-top: var(--spacing-5);
  padding-top: var(--spacing-4);
  border-top: 1px solid rgba(71, 85, 105, 0.3);
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-1);
}

.stat-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
}

.stat-value {
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.stat-value.peak {
  color: var(--color-error);
}

.stat-value.low {
  color: var(--color-success);
}

/* Tooltip styles */
:deep(.heatmap-tooltip) {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-3);
  min-width: 150px;
}

:deep(.tooltip-header) {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin-bottom: var(--spacing-2);
  padding-bottom: var(--spacing-2);
  border-bottom: 1px solid var(--border-default);
}

:deep(.tooltip-row) {
  display: flex;
  justify-content: space-between;
  margin-bottom: var(--spacing-1);
}

:deep(.tooltip-label) {
  color: var(--text-secondary);
  font-size: var(--text-xs);
}

:deep(.tooltip-value) {
  font-weight: var(--font-medium);
  color: var(--text-primary);
  font-size: var(--text-xs);
}

:deep(.tooltip-value.critical) {
  color: var(--color-error);
}

:deep(.tooltip-value.high) {
  color: var(--color-warning);
}

:deep(.tooltip-value.medium) {
  color: var(--chart-blue);
}

:deep(.tooltip-value.low) {
  color: var(--color-success);
}

/* Responsive */
@media (max-width: 768px) {
  .heatmap-header {
    flex-direction: column;
    gap: var(--spacing-3);
    align-items: stretch;
  }

  .header-actions {
    flex-wrap: wrap;
  }

  .metric-select,
  .time-select {
    flex: 1;
    min-width: 120px;
  }

  .heatmap-stats {
    gap: var(--spacing-4);
  }

  .stat-value {
    font-size: var(--text-base);
  }
}
</style>
