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
      <h3>{{ title || t('visualizations.resourceHeatmap.defaultTitle') }}</h3>
      <div class="header-actions">
        <select v-model="selectedMetric" @change="updateData" class="metric-select">
          <option value="cpu">{{ t('visualizations.resourceHeatmap.cpuUsage') }}</option>
          <option value="memory">{{ t('visualizations.resourceHeatmap.memoryUsage') }}</option>
          <option value="disk">{{ t('visualizations.resourceHeatmap.diskIo') }}</option>
          <option value="network">{{ t('visualizations.resourceHeatmap.networkIo') }}</option>
        </select>
        <select v-model="timeRange" @change="fetchData" class="time-select">
          <option value="1h">{{ t('visualizations.resourceHeatmap.lastHour') }}</option>
          <option value="6h">{{ t('visualizations.resourceHeatmap.last6Hours') }}</option>
          <option value="24h">{{ t('visualizations.resourceHeatmap.last24Hours') }}</option>
          <option value="7d">{{ t('visualizations.resourceHeatmap.last7Days') }}</option>
        </select>
        <button @click="fetchData" class="refresh-btn" :disabled="isLoading">
          <Icon name="sync" />
        </button>
      </div>
    </div>

    <div v-if="isLoading" class="loading-state">
      <Icon name="spinner" class="animate-spin" />
      <span>{{ t('visualizations.resourceHeatmap.loadingData') }}</span>
    </div>

    <div v-else-if="error" class="error-state">
      <Icon name="exclamation-triangle" />
      <span>{{ error }}</span>
      <button @click="fetchData" class="retry-btn">{{ t('visualizations.resourceHeatmap.retry') }}</button>
    </div>

    <div v-else class="heatmap-container">
      <!-- ApexCharts Heatmap — only mount once chartSeries has data; mounting
           against an empty series triggers the vue3-apexcharts "Element not
           found" race (chart instance is created before the parent has any
           rows to lay out, and the SVG target it looks for never exists). -->
      <apexchart
        v-if="chartSeries.length > 0"
        ref="chartRef"
        type="heatmap"
        :height="height"
        :options="chartOptions"
        :series="chartSeries"
      />
      <div v-else class="no-data-state">
        <Icon name="chart-bar" />
        <span>{{ t('visualizations.resourceHeatmap.noData') }}</span>
      </div>

      <!-- Legend -->
      <div class="heatmap-legend">
        <span class="legend-label">{{ t('visualizations.resourceHeatmap.legendLow') }}</span>
        <div class="legend-gradient"></div>
        <span class="legend-label">{{ t('visualizations.resourceHeatmap.legendHigh') }}</span>
      </div>

      <!-- Summary Stats -->
      <div class="heatmap-stats">
        <div class="stat-item">
          <span class="stat-label">{{ t('visualizations.resourceHeatmap.peak') }}</span>
          <span class="stat-value peak">{{ peakValue }}%</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">{{ t('visualizations.resourceHeatmap.average') }}</span>
          <span class="stat-value">{{ averageValue }}%</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">{{ t('visualizations.resourceHeatmap.minimum') }}</span>
          <span class="stat-value low">{{ minValue }}%</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import VueApexCharts from 'vue3-apexcharts'
import type { ApexOptions } from 'apexcharts'
import { useResourceMetrics } from '@/composables/visualizations/useResourceMetrics'
import { usePollingJob } from '@/composables/usePollingJob'
import { getCssVar } from '@/composables/useCssVars'

const { t } = useI18n()

const apexchart = VueApexCharts

// Props
interface Props {
  title?: string
  height?: number
  refreshInterval?: number
  machine?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: undefined,
  height: 350,
  refreshInterval: 60000,
  machine: 'all'
})

// Emit events
const emit = defineEmits<{
  (e: 'cell-click', data: { machine: string; time: string; value: number }): void
}>()

// State — fetching and metrics state delegated to composable
const { isLoading, error, selectedMetric, timeRange, heatmapData, fetchData, updateData } =
  useResourceMetrics(() => props.machine)
const chartRef = ref<InstanceType<typeof VueApexCharts> | null>(null)

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
          { from: 0, to: 20, color: getCssVar('--color-info-dark'), name: t('visualizations.resourceHeatmap.rangeLow') },
          { from: 21, to: 40, color: getCssVar('--color-info-hover'), name: t('visualizations.resourceHeatmap.rangeModerate') },
          { from: 41, to: 60, color: getCssVar('--chart-blue'), name: t('visualizations.resourceHeatmap.rangeMedium') },
          { from: 61, to: 80, color: getCssVar('--color-warning'), name: t('visualizations.resourceHeatmap.rangeHigh') },
          { from: 81, to: 100, color: getCssVar('--color-error'), name: t('visualizations.resourceHeatmap.rangeCritical') }
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
    cpu: t('visualizations.resourceHeatmap.cpuUsage'),
    memory: t('visualizations.resourceHeatmap.memoryUsage'),
    disk: t('visualizations.resourceHeatmap.diskIo'),
    network: t('visualizations.resourceHeatmap.networkIo')
  }
  return labels[selectedMetric.value] || t('visualizations.resourceHeatmap.usage')
}

function getValueClass(value: number): string {
  if (value >= 80) return 'critical'
  if (value >= 60) return 'high'
  if (value >= 40) return 'medium'
  return 'low'
}

// Lifecycle
const { start: _startRefresh, stop: _stopRefresh } = usePollingJob(
  async () => { await fetchData(); return null },
  { intervalMs: props.refreshInterval || 0, maxAttempts: Number.MAX_SAFE_INTEGER }
)

onMounted(() => {
  fetchData()

  if (props.refreshInterval > 0) {
    _startRefresh('')
  }
})

// Watch for prop changes
watch(() => props.machine, () => {
  fetchData()
})

// Cleanup
onUnmounted(() => {
  _stopRefresh()
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
  margin: var(--spacing-0);
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
.metric-select:focus-visible,
.time-select:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
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
.error-state,
.no-data-state {
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
