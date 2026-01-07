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

/**
 * Get CSS variable value from the document
 * Issue #704: Use design tokens for theming
 */
const getCssVar = (name: string, fallback: string): string => {
  if (typeof document === 'undefined') return fallback
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

// AutoBot theme colors using CSS custom properties (Issue #704)
// These values are read from design-tokens.css and adapt to dark/light theme
const darkTheme: any = {
  chart: {
    background: 'transparent',
    foreColor: getCssVar('--text-primary', '#e2e8f0'),
    fontFamily: getCssVar('--font-sans', 'Inter, system-ui, sans-serif'),
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
  // Chart colors from design tokens (Issue #704)
  colors: [
    getCssVar('--chart-blue', '#3b82f6'),
    getCssVar('--chart-green', '#22c55e'),
    getCssVar('--chart-yellow', '#f59e0b'),
    getCssVar('--chart-red', '#ef4444'),
    getCssVar('--chart-purple', '#8b5cf6'),
    getCssVar('--chart-cyan', '#06b6d4'),
    getCssVar('--chart-pink', '#ec4899'),
    getCssVar('--chart-orange', '#f97316'),
    getCssVar('--chart-teal', '#14b8a6'),
    getCssVar('--chart-indigo', '#6366f1')
  ],
  grid: {
    show: true,
    borderColor: getCssVar('--bg-tertiary', '#334155'),
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
        colors: getCssVar('--text-secondary', '#94a3b8'),
        fontSize: '12px'
      }
    },
    axisBorder: {
      show: true,
      color: getCssVar('--border-default', '#475569')
    },
    axisTicks: {
      show: true,
      color: getCssVar('--border-default', '#475569')
    }
  },
  yaxis: {
    labels: {
      style: {
        colors: getCssVar('--text-secondary', '#94a3b8'),
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
/**
 * Issue #704: CSS Design System - Using design tokens
 * All colors reference CSS custom properties from design-tokens.css
 */
.base-chart {
  position: relative;
  width: 100%;
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  padding: var(--spacing-md);
  border: 1px solid var(--border-subtle);
}

.chart-loading {
  opacity: 0.7;
}

.chart-header {
  margin-bottom: var(--spacing-md);
  padding-bottom: var(--spacing-sm);
  border-bottom: 1px solid var(--border-subtle);
}

.chart-title {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0;
}

.chart-subtitle {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-top: var(--spacing-1);
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
  gap: var(--spacing-sm);
  color: var(--text-secondary);
}

.chart-loading-overlay i,
.chart-error i,
.chart-no-data i {
  font-size: 32px;
}

.chart-error {
  color: var(--color-error-light);
}

.chart-error i {
  color: var(--color-error);
}

.chart-no-data i {
  color: var(--text-tertiary);
}

/* Deep styles for ApexCharts - using design tokens */
:deep(.apexcharts-canvas) {
  background: transparent !important;
}

:deep(.apexcharts-tooltip) {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border-default) !important;
  border-radius: var(--radius-md) !important;
  box-shadow: var(--shadow-lg) !important;
}

:deep(.apexcharts-tooltip-title) {
  background: var(--bg-tertiary) !important;
  border-bottom: 1px solid var(--border-default) !important;
  color: var(--text-primary) !important;
}

:deep(.apexcharts-tooltip-series-group) {
  background: transparent !important;
}

:deep(.apexcharts-tooltip-text) {
  color: var(--text-primary) !important;
}

:deep(.apexcharts-xaxistooltip),
:deep(.apexcharts-yaxistooltip) {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border-default) !important;
  color: var(--text-primary) !important;
}

:deep(.apexcharts-menu) {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border-default) !important;
}

:deep(.apexcharts-menu-item:hover) {
  background: var(--bg-tertiary) !important;
}

:deep(.apexcharts-toolbar) {
  z-index: var(--z-10);
}

:deep(.apexcharts-zoom-icon),
:deep(.apexcharts-zoomin-icon),
:deep(.apexcharts-zoomout-icon),
:deep(.apexcharts-reset-icon),
:deep(.apexcharts-pan-icon),
:deep(.apexcharts-selection-icon),
:deep(.apexcharts-menu-icon) {
  color: var(--text-secondary) !important;
}

:deep(.apexcharts-zoom-icon:hover),
:deep(.apexcharts-zoomin-icon:hover),
:deep(.apexcharts-zoomout-icon:hover),
:deep(.apexcharts-reset-icon:hover),
:deep(.apexcharts-pan-icon:hover),
:deep(.apexcharts-selection-icon:hover),
:deep(.apexcharts-menu-icon:hover) {
  color: var(--text-primary) !important;
}

:deep(.apexcharts-zoom-icon.apexcharts-selected),
:deep(.apexcharts-pan-icon.apexcharts-selected),
:deep(.apexcharts-selection-icon.apexcharts-selected) {
  color: var(--color-primary) !important;
}
</style>
