<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  ModuleImportsChart.vue - Bar chart showing modules with most imports
-->
<template>
  <BaseChart
    type="bar"
    :height="height"
    :series="chartSeries"
    :options="chartOptions"
    :title="title"
    :subtitle="subtitle"
    :loading="loading"
    :error="error"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import BaseChart from './BaseChart.vue'
import type { ApexOptions } from 'apexcharts'

/**
 * Get CSS variable value from the document
 * Issue #704: Use design tokens for theming
 */
function getCssVar(name: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

interface ModuleData {
  path: string
  name: string
  package: string
  import_count: number
  functions: number
  classes: number
}

interface Props {
  data: ModuleData[]
  title?: string
  subtitle?: string
  height?: number | string
  maxModules?: number
  loading?: boolean
  error?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: 'Modules with Most Imports',
  subtitle: 'Files with highest dependency count',
  height: 400,
  maxModules: 15,
  loading: false,
  error: ''
})

// Sort and limit data
const sortedData = computed(() => {
  return [...props.data]
    .sort((a, b) => b.import_count - a.import_count)
    .slice(0, props.maxModules)
})

// Transform data for bar chart
const chartSeries = computed(() => [
  {
    name: 'Imports',
    data: sortedData.value.map((item) => item.import_count)
  }
])

const chartOptions = computed<ApexOptions>(() => ({
  chart: {
    type: 'bar'
  },
  plotOptions: {
    bar: {
      horizontal: true,
      borderRadius: 4,
      barHeight: '70%',
      distributed: false
    }
  },
  // Issue #704: Using design tokens with fallbacks for SSR compatibility
  colors: [getCssVar('--chart-purple', '#8b5cf6')],
  xaxis: {
    categories: sortedData.value.map((item) => truncatePath(item.path)),
    title: {
      text: 'Number of Imports',
      style: {
        fontSize: '12px',
        color: getCssVar('--text-secondary', '#94a3b8')
      }
    }
  },
  yaxis: {
    labels: {
      style: {
        fontSize: '11px'
      },
      maxWidth: 200
    }
  },
  dataLabels: {
    enabled: true,
    formatter: (value: number) => value.toString(),
    style: {
      fontSize: '11px',
      fontWeight: 600
    }
  },
  // Issue #704: Tooltip uses design token fallbacks for inline styles
  tooltip: {
    custom: ({ dataPointIndex }: { dataPointIndex: number }) => {
      const item = sortedData.value[dataPointIndex]
      if (!item) return ''

      // Get design token colors for tooltip (inline styles require literal values)
      const bgElevated = getCssVar('--bg-elevated', '#1e293b')
      const borderDefault = getCssVar('--border-default', '#475569')
      const textPrimary = getCssVar('--text-primary', '#e2e8f0')
      const textSecondary = getCssVar('--text-secondary', '#94a3b8')
      const chartPurple = getCssVar('--chart-purple', '#8b5cf6')
      const colorSuccess = getCssVar('--color-success', '#10b981')
      const colorWarning = getCssVar('--color-warning', '#f59e0b')

      return `
        <div style="background: ${bgElevated}; border: 1px solid ${borderDefault}; border-radius: 6px; padding: 12px; max-width: 350px;">
          <div style="font-weight: 600; color: ${textPrimary}; margin-bottom: 8px; word-break: break-all;">
            ${item.path}
          </div>
          <div style="color: ${textSecondary}; display: flex; flex-direction: column; gap: 4px;">
            <div><span style="color: ${chartPurple}; font-weight: 600;">${item.import_count}</span> imports</div>
            <div><span style="color: ${colorSuccess};">${item.functions}</span> functions</div>
            <div><span style="color: ${colorWarning};">${item.classes}</span> classes</div>
          </div>
        </div>
      `
    }
  },
  legend: {
    show: false
  }
}))

// Truncate file path for display
function truncatePath(path: string, maxLength: number = 30): string {
  if (!path) return ''
  if (path.length <= maxLength) return path

  const parts = path.split('/')
  const filename = parts[parts.length - 1]

  if (filename.length >= maxLength - 3) {
    return '...' + filename.slice(-(maxLength - 3))
  }

  return '.../' + filename
}
</script>
