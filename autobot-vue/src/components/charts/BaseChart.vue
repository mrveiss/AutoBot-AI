<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  BaseChart.vue - Base ApexCharts component with AutoBot dark theme
  Provides consistent chart styling across all analytics visualizations
-->
<template>
  <div class="base-chart" :class="{ 'chart-loading': loading }">
    <div v-if="title" class="chart-header">
      <h3 class="chart-title">{{ title }}</h3>
      <span v-if="subtitle" class="chart-subtitle">{{ subtitle }}</span>
    </div>
    <div v-if="loading" class="chart-loading-overlay">
      <i class="fas fa-spinner fa-spin"></i>
      <span>Loading chart...</span>
    </div>
    <div v-else-if="error" class="chart-error">
      <i class="fas fa-exclamation-triangle"></i>
      <span>{{ error }}</span>
    </div>
    <div v-else-if="!hasData" class="chart-no-data">
      <i class="fas fa-chart-bar"></i>
      <span>No data available</span>
    </div>
    <apexchart
      v-else
      ref="chartRef"
      :type="(type as any)"
      :height="height"
      :width="width"
      :options="(mergedOptions as any)"
      :series="safeSeries"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import VueApexCharts from 'vue3-apexcharts'
import type { ApexOptions } from 'apexcharts'

// Register component locally
const apexchart = VueApexCharts

// Props
interface Props {
  type?: 'line' | 'area' | 'bar' | 'pie' | 'donut' | 'radialBar' | 'scatter' | 'bubble' | 'heatmap' | 'treemap' | 'polarArea' | 'radar'
  height?: string | number
  width?: string | number
  series: ApexAxisChartSeries | ApexNonAxisChartSeries
  options?: ApexOptions
  title?: string
  subtitle?: string
  loading?: boolean
  error?: string
}

const props = withDefaults(defineProps<Props>(), {
  type: 'bar',
  height: 350,
  width: '100%',
  options: () => ({}),
  loading: false,
  error: ''
})

// Refs
const chartRef = ref<InstanceType<typeof VueApexCharts> | null>(null)

// Safe series - ensures we always pass a valid array to ApexCharts
const safeSeries = computed(() => {
  if (!props.series || !Array.isArray(props.series)) {
    return []
  }
  return props.series
})

// Check if there's data to display
const hasData = computed(() => {
  if (safeSeries.value.length === 0) return false

  // For pie/donut charts, check if values array has data
  if (props.type === 'pie' || props.type === 'donut') {
    return safeSeries.value.some((value) => typeof value === 'number' && value > 0)
  }

  // For other charts, check if any series has data
  return safeSeries.value.some((s) => {
    if (typeof s === 'number') return s > 0
    if (s && 'data' in s && Array.isArray(s.data)) return s.data.length > 0
    return false
  })
})

// AutoBot dark theme colors (cast as any to allow extended ApexCharts options)
const darkTheme: any = {
  chart: {
    background: 'transparent',
    foreColor: '#e2e8f0',
    fontFamily: 'Inter, system-ui, sans-serif',
    toolbar: {
      show: true,
      tools: {
        download: true,
        selection: true,
        zoom: true,
        zoomin: true,
        zoomout: true,
        pan: true,
        reset: true
      },
      autoSelected: 'zoom'
    },
    animations: {
      enabled: true,
      easing: 'easeinout',
      speed: 400,
      animateGradually: {
        enabled: true,
        delay: 50
      },
      dynamicAnimation: {
        enabled: true,
        speed: 300
      }
    },
    dropShadow: {
      enabled: false
    }
  },
  theme: {
    mode: 'dark',
    palette: 'palette1'
  },
  colors: [
    '#3b82f6', // Blue (primary)
    '#10b981', // Green (success)
    '#f59e0b', // Amber (warning)
    '#ef4444', // Red (error)
    '#8b5cf6', // Purple
    '#06b6d4', // Cyan
    '#ec4899', // Pink
    '#f97316', // Orange
    '#84cc16', // Lime
    '#6366f1'  // Indigo
  ],
  grid: {
    show: true,
    borderColor: '#334155',
    strokeDashArray: 3,
    position: 'back',
    xaxis: {
      lines: {
        show: false
      }
    },
    yaxis: {
      lines: {
        show: true
      }
    },
    padding: {
      top: 10,
      right: 10,
      bottom: 0,
      left: 10
    }
  },
  xaxis: {
    labels: {
      style: {
        colors: '#94a3b8',
        fontSize: '12px'
      }
    },
    axisBorder: {
      show: true,
      color: '#475569'
    },
    axisTicks: {
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
    style: {
      fontSize: '12px',
      fontFamily: 'Inter, system-ui, sans-serif'
    },
    x: {
      show: true
    },
    y: {
      formatter: (value: number) => {
        if (typeof value === 'number') {
          return value.toLocaleString()
        }
        return String(value)
      }
    }
  },
  legend: {
    show: true,
    position: 'bottom',
    horizontalAlign: 'center',
    fontSize: '12px',
    fontFamily: 'Inter, system-ui, sans-serif',
    fontWeight: 400,
    labels: {
      colors: '#e2e8f0'
    },
    markers: {
      width: 12,
      height: 12,
      radius: 2
    },
    itemMargin: {
      horizontal: 10,
      vertical: 5
    }
  },
  dataLabels: {
    enabled: false,
    style: {
      fontSize: '11px',
      fontFamily: 'Inter, system-ui, sans-serif',
      fontWeight: 500,
      colors: ['#fff']
    },
    background: {
      enabled: true,
      foreColor: '#1e293b',
      borderRadius: 2,
      padding: 4,
      opacity: 0.9,
      borderWidth: 0
    }
  },
  stroke: {
    show: true,
    curve: 'smooth',
    lineCap: 'round',
    width: 2
  },
  fill: {
    type: 'solid',
    opacity: 0.85
  },
  plotOptions: {
    bar: {
      horizontal: false,
      borderRadius: 4,
      columnWidth: '60%',
      dataLabels: {
        position: 'top'
      }
    },
    pie: {
      donut: {
        size: '55%',
        labels: {
          show: true,
          name: {
            show: true,
            fontSize: '14px',
            fontFamily: 'Inter, system-ui, sans-serif',
            color: '#e2e8f0'
          },
          value: {
            show: true,
            fontSize: '22px',
            fontFamily: 'Inter, system-ui, sans-serif',
            color: '#e2e8f0',
            formatter: (val: string) => val
          },
          total: {
            show: true,
            showAlways: false,
            label: 'Total',
            fontSize: '14px',
            fontFamily: 'Inter, system-ui, sans-serif',
            color: '#94a3b8'
          }
        }
      }
    },
    radialBar: {
      hollow: {
        size: '60%'
      },
      track: {
        background: '#334155'
      },
      dataLabels: {
        name: {
          fontSize: '14px',
          color: '#e2e8f0'
        },
        value: {
          fontSize: '24px',
          color: '#e2e8f0'
        }
      }
    },
    treemap: {
      enableShades: true,
      shadeIntensity: 0.5,
      distributed: false,
      useFillColorAsStroke: false
    },
    heatmap: {
      radius: 2,
      enableShades: true,
      shadeIntensity: 0.5,
      colorScale: {
        ranges: [
          { from: 0, to: 25, color: '#1e3a5f', name: 'low' },
          { from: 26, to: 50, color: '#3b82f6', name: 'medium' },
          { from: 51, to: 75, color: '#f59e0b', name: 'high' },
          { from: 76, to: 100, color: '#ef4444', name: 'critical' }
        ]
      }
    }
  },
  states: {
    hover: {
      filter: {
        type: 'lighten',
        value: 0.1
      }
    },
    active: {
      filter: {
        type: 'darken',
        value: 0.1
      }
    }
  },
  responsive: [
    {
      breakpoint: 768,
      options: {
        chart: {
          toolbar: {
            show: false
          }
        },
        legend: {
          position: 'bottom',
          offsetY: 0
        }
      }
    }
  ]
}

// Deep merge options with dark theme (handles arrays properly)
const deepMerge = (target: Record<string, unknown>, source: Record<string, unknown>): Record<string, unknown> => {
  const output = { ...target }
  for (const key of Object.keys(source)) {
    const sourceValue = source[key]
    const targetValue = target[key]

    // Arrays should be replaced, not merged (prevents responsive array corruption)
    if (Array.isArray(sourceValue)) {
      output[key] = [...sourceValue]
    } else if (
      sourceValue !== null &&
      typeof sourceValue === 'object' &&
      !Array.isArray(sourceValue) &&
      targetValue !== null &&
      typeof targetValue === 'object' &&
      !Array.isArray(targetValue)
    ) {
      // Deep merge objects
      output[key] = deepMerge(targetValue as Record<string, unknown>, sourceValue as Record<string, unknown>)
    } else {
      output[key] = sourceValue
    }
  }
  return output
}

// Merged options with dark theme as base
const mergedOptions = computed<ApexOptions>(() => {
  return deepMerge(darkTheme as Record<string, unknown>, props.options as Record<string, unknown>) as ApexOptions
})

// Expose methods
const updateSeries = (newSeries: ApexAxisChartSeries | ApexNonAxisChartSeries) => {
  chartRef.value?.updateSeries(newSeries)
}

const updateOptions = (newOptions: ApexOptions) => {
  chartRef.value?.updateOptions(newOptions)
}

const refresh = () => {
  chartRef.value?.refresh()
}

defineExpose({
  updateSeries,
  updateOptions,
  refresh,
  chartRef
})

// Watch for series changes
watch(
  () => props.series,
  () => {
    // Chart will update automatically through props
  },
  { deep: true }
)
</script>

<style scoped>
.base-chart {
  position: relative;
  width: 100%;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 8px;
  padding: 16px;
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.chart-loading {
  opacity: 0.7;
}

.chart-header {
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(71, 85, 105, 0.5);
}

.chart-title {
  font-size: 16px;
  font-weight: 600;
  color: #e2e8f0;
  margin: 0;
}

.chart-subtitle {
  font-size: 12px;
  color: #94a3b8;
  margin-top: 4px;
  display: block;
}

.chart-loading-overlay,
.chart-error,
.chart-no-data {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  gap: 12px;
  color: #94a3b8;
}

.chart-loading-overlay i,
.chart-error i,
.chart-no-data i {
  font-size: 32px;
}

.chart-error {
  color: #f87171;
}

.chart-error i {
  color: #ef4444;
}

.chart-no-data i {
  color: #64748b;
}

/* Deep styles for ApexCharts */
:deep(.apexcharts-canvas) {
  background: transparent !important;
}

:deep(.apexcharts-tooltip) {
  background: #1e293b !important;
  border: 1px solid #475569 !important;
  border-radius: 6px !important;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3) !important;
}

:deep(.apexcharts-tooltip-title) {
  background: #334155 !important;
  border-bottom: 1px solid #475569 !important;
  color: #e2e8f0 !important;
}

:deep(.apexcharts-tooltip-series-group) {
  background: transparent !important;
}

:deep(.apexcharts-tooltip-text) {
  color: #e2e8f0 !important;
}

:deep(.apexcharts-xaxistooltip),
:deep(.apexcharts-yaxistooltip) {
  background: #1e293b !important;
  border: 1px solid #475569 !important;
  color: #e2e8f0 !important;
}

:deep(.apexcharts-menu) {
  background: #1e293b !important;
  border: 1px solid #475569 !important;
}

:deep(.apexcharts-menu-item:hover) {
  background: #334155 !important;
}

:deep(.apexcharts-toolbar) {
  z-index: 10;
}

:deep(.apexcharts-zoom-icon),
:deep(.apexcharts-zoomin-icon),
:deep(.apexcharts-zoomout-icon),
:deep(.apexcharts-reset-icon),
:deep(.apexcharts-pan-icon),
:deep(.apexcharts-selection-icon),
:deep(.apexcharts-menu-icon) {
  color: #94a3b8 !important;
}

:deep(.apexcharts-zoom-icon:hover),
:deep(.apexcharts-zoomin-icon:hover),
:deep(.apexcharts-zoomout-icon:hover),
:deep(.apexcharts-reset-icon:hover),
:deep(.apexcharts-pan-icon:hover),
:deep(.apexcharts-selection-icon:hover),
:deep(.apexcharts-menu-icon:hover) {
  color: #e2e8f0 !important;
}

:deep(.apexcharts-zoom-icon.apexcharts-selected),
:deep(.apexcharts-pan-icon.apexcharts-selected),
:deep(.apexcharts-selection-icon.apexcharts-selected) {
  color: #3b82f6 !important;
}
</style>
