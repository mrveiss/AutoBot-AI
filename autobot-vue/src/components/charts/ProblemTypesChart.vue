<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  ProblemTypesChart.vue - Pie chart for problem type distribution
-->
<template>
  <BaseChart
    type="pie"
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

interface ProblemTypeData {
  type?: string
  name?: string
  count?: number
  value?: number
}

interface Props {
  data: ProblemTypeData[]
  title?: string
  subtitle?: string
  height?: number | string
  loading?: boolean
  error?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: 'Problem Types Distribution',
  subtitle: '',
  height: 350,
  loading: false,
  error: ''
})

// Transform data for pie chart - support both count/value and type/name formats
const chartSeries = computed(() => {
  return props.data.map((item) => item.count ?? item.value ?? 0)
})

const chartOptions = computed<ApexOptions>(() => ({
  labels: props.data.map((item) => item.type ?? item.name ?? 'Unknown'),
  colors: getColorForTypes(props.data.map((item) => item.type ?? item.name ?? 'unknown')),
  legend: {
    position: 'right',
    offsetY: 0,
    fontSize: '13px'
  },
  tooltip: {
    y: {
      formatter: (value: number) => `${value} problems`
    }
  },
  dataLabels: {
    enabled: true,
    formatter: (val: number) => `${val.toFixed(1)}%`
  },
  plotOptions: {
    pie: {
      expandOnClick: true,
      donut: {
        size: '0%'
      }
    }
  },
  responsive: [
    {
      breakpoint: 600,
      options: {
        legend: {
          position: 'bottom'
        }
      }
    }
  ]
}))

/**
 * Get CSS variable value from the document
 * Issue #704: Use design tokens for theming
 */
function getCssVar(name: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

// Get colors based on problem types
// Issue #704: Using design tokens with fallbacks for SSR compatibility
function getColorForTypes(types: string[]): string[] {
  const typeColors: Record<string, string> = {
    // Severity-based
    error: getCssVar('--color-error', '#ef4444'),
    warning: getCssVar('--color-warning', '#f59e0b'),
    info: getCssVar('--color-info', '#3b82f6'),
    hint: getCssVar('--color-success', '#10b981'),

    // Category-based
    security: getCssVar('--color-error', '#ef4444'),
    race_condition: getCssVar('--chart-orange', '#f97316'),
    performance: getCssVar('--color-warning', '#f59e0b'),
    style: getCssVar('--chart-purple', '#8b5cf6'),
    complexity: getCssVar('--chart-pink', '#ec4899'),
    unused: getCssVar('--text-tertiary', '#64748b'),
    deprecated: getCssVar('--text-secondary', '#94a3b8'),
    type_error: getCssVar('--chart-cyan', '#06b6d4'),
    syntax: getCssVar('--color-error', '#ef4444'),
    logic: getCssVar('--color-warning', '#f59e0b'),
    documentation: getCssVar('--color-info', '#3b82f6'),
    maintainability: getCssVar('--color-success', '#10b981'),
    best_practice: getCssVar('--chart-lime', '#84cc16'),

    // Default
    other: getCssVar('--chart-indigo', '#6366f1')
  }

  return types.map((type) => {
    const key = type.toLowerCase().replace(/[^a-z_]/g, '_')
    return typeColors[key] || typeColors.other
  })
}
</script>
