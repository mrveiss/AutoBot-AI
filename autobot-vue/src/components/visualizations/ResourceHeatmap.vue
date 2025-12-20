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
    foreColor: '#e2e8f0',
    fontFamily: 'Inter, system-ui, sans-serif',
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
  colors: ['#3b82f6'],
  plotOptions: {
    heatmap: {
      shadeIntensity: 0.5,
      radius: 2,
      useFillColorAsStroke: false,
      colorScale: {
        ranges: [
          { from: 0, to: 20, color: '#1e3a5f', name: 'Low' },
          { from: 21, to: 40, color: '#2563eb', name: 'Moderate' },
          { from: 41, to: 60, color: '#3b82f6', name: 'Medium' },
          { from: 61, to: 80, color: '#f59e0b', name: 'High' },
          { from: 81, to: 100, color: '#ef4444', name: 'Critical' }
        ]
      }
    }
  },
  stroke: {
    width: 1,
    colors: ['#1e293b']
  },
  xaxis: {
    type: 'category',
    labels: {
      style: {
        colors: '#94a3b8',
        fontSize: '11px'
      },
      rotate: -45,
      rotateAlways: false
    },
    axisBorder: {
      show: true,
      color: '#475569'
    }
  },
  yaxis: {
    labels: {
      style: {
        colors: '#94a3b8',
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

<style scoped>
.resource-heatmap {
  background: rgba(30, 41, 59, 0.5);
  border-radius: 12px;
  padding: 20px;
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.heatmap-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(71, 85, 105, 0.5);
}

.heatmap-header h3 {
  font-size: 18px;
  font-weight: 600;
  color: #e2e8f0;
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.metric-select,
.time-select {
  padding: 8px 12px;
  background: rgba(51, 65, 85, 0.5);
  border: 1px solid rgba(71, 85, 105, 0.5);
  border-radius: 6px;
  color: #e2e8f0;
  font-size: 13px;
  cursor: pointer;
  transition: border-color 0.2s;
}

.metric-select:focus,
.time-select:focus {
  outline: none;
  border-color: #3b82f6;
}

.refresh-btn {
  padding: 8px 12px;
  background: transparent;
  border: 1px solid rgba(71, 85, 105, 0.5);
  border-radius: 6px;
  color: #94a3b8;
  cursor: pointer;
  transition: all 0.2s;
}

.refresh-btn:hover:not(:disabled) {
  background: rgba(59, 130, 246, 0.1);
  border-color: #3b82f6;
  color: #3b82f6;
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
  gap: 12px;
  color: #94a3b8;
}

.error-state {
  color: #f87171;
}

.retry-btn {
  margin-top: 8px;
  padding: 8px 16px;
  background: rgba(59, 130, 246, 0.2);
  border: 1px solid #3b82f6;
  border-radius: 6px;
  color: #3b82f6;
  cursor: pointer;
  transition: background 0.2s;
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
  gap: 12px;
  margin-top: 16px;
}

.legend-label {
  font-size: 12px;
  color: #94a3b8;
}

.legend-gradient {
  width: 200px;
  height: 12px;
  border-radius: 6px;
  background: linear-gradient(
    90deg,
    #1e3a5f 0%,
    #2563eb 25%,
    #3b82f6 50%,
    #f59e0b 75%,
    #ef4444 100%
  );
}

.heatmap-stats {
  display: flex;
  justify-content: center;
  gap: 32px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid rgba(71, 85, 105, 0.3);
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.stat-label {
  font-size: 12px;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.stat-value {
  font-size: 20px;
  font-weight: 600;
  color: #e2e8f0;
}

.stat-value.peak {
  color: #ef4444;
}

.stat-value.low {
  color: #10b981;
}

/* Tooltip styles */
:deep(.heatmap-tooltip) {
  background: #1e293b;
  border: 1px solid #475569;
  border-radius: 8px;
  padding: 12px;
  min-width: 150px;
}

:deep(.tooltip-header) {
  font-weight: 600;
  color: #e2e8f0;
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid #475569;
}

:deep(.tooltip-row) {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
}

:deep(.tooltip-label) {
  color: #94a3b8;
  font-size: 12px;
}

:deep(.tooltip-value) {
  font-weight: 500;
  color: #e2e8f0;
  font-size: 12px;
}

:deep(.tooltip-value.critical) {
  color: #ef4444;
}

:deep(.tooltip-value.high) {
  color: #f59e0b;
}

:deep(.tooltip-value.medium) {
  color: #3b82f6;
}

:deep(.tooltip-value.low) {
  color: #10b981;
}

/* Responsive */
@media (max-width: 768px) {
  .heatmap-header {
    flex-direction: column;
    gap: 12px;
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
    gap: 16px;
  }

  .stat-value {
    font-size: 16px;
  }
}
</style>
