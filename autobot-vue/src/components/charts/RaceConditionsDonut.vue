<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  RaceConditionsDonut.vue - Donut chart for race condition categories
-->
<template>
  <BaseChart
    type="donut"
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

interface RaceConditionData {
  category?: string
  name?: string
  count?: number
  value?: number
}

interface Props {
  data: RaceConditionData[]
  title?: string
  subtitle?: string
  height?: number | string
  loading?: boolean
  error?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: 'Race Conditions by Category',
  subtitle: '',
  height: 350,
  loading: false,
  error: ''
})

// Transform data for donut chart - support both count/value and category/name formats
const chartSeries = computed(() => {
  return props.data.map((item) => item.count ?? item.value ?? 0)
})

const totalCount = computed(() => {
  return props.data.reduce((sum, item) => sum + (item.count ?? item.value ?? 0), 0)
})

const chartOptions = computed<ApexOptions>(() => ({
  labels: props.data.map((item) => formatCategoryLabel(item.category ?? item.name ?? 'unknown')),
  colors: getCategoryColors(props.data.map((item) => item.category ?? item.name ?? 'unknown')),
  legend: {
    position: 'right',
    offsetY: 0,
    fontSize: '12px'
  },
  tooltip: {
    y: {
      formatter: (value: number) => `${value} issues`
    }
  },
  dataLabels: {
    enabled: true,
    formatter: (val: number, opts: { seriesIndex: number }) => {
      const item = props.data[opts.seriesIndex]
      const count = item?.count ?? item?.value ?? 0
      if (count === 0) return ''
      return count.toString()
    }
  },
  plotOptions: {
    pie: {
      expandOnClick: true,
      donut: {
        size: '55%',
        labels: {
          show: true,
          name: {
            show: true,
            fontSize: '14px',
            color: getCssVar('--text-primary', '#e2e8f0')
          },
          value: {
            show: true,
            fontSize: '24px',
            color: getCssVar('--text-primary', '#e2e8f0'),
            formatter: () => totalCount.value.toString()
          },
          total: {
            show: true,
            showAlways: true,
            label: 'Total Issues',
            fontSize: '12px',
            color: getCssVar('--text-secondary', '#94a3b8'),
            formatter: () => totalCount.value.toString()
          }
        }
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

// Get colors based on race condition categories
// Issue #704: Using design tokens with fallbacks for SSR compatibility
function getCategoryColors(categories: string[]): string[] {
  const categoryColors: Record<string, string> = {
    // Thread safety issues
    thread_unsafe_singleton: getCssVar('--color-error', '#ef4444'),
    unprotected_global_state: getCssVar('--chart-orange', '#f97316'),
    unprotected_global_modification: getCssVar('--chart-orange', '#f97316'),
    unprotected_subscript_assignment: getCssVar('--color-warning', '#f59e0b'),
    unprotected_mutating_method: getCssVar('--chart-yellow', '#eab308'),

    // Async issues
    async_shared_state: getCssVar('--chart-purple', '#8b5cf6'),
    async_global_modification: getCssVar('--chart-purple-light', '#a855f7'),

    // File operations
    file_write_without_lock: getCssVar('--chart-cyan', '#06b6d4'),
    file_writes_without_locking: getCssVar('--chart-cyan', '#06b6d4'),

    // Read-modify-write
    read_modify_write: getCssVar('--chart-pink', '#ec4899'),
    read_modify_write_pattern: getCssVar('--chart-pink', '#ec4899'),

    // Default
    other: getCssVar('--chart-indigo', '#6366f1')
  }

  return categories.map((category) => {
    const key = category.toLowerCase().replace(/[^a-z_]/g, '_').replace(/__+/g, '_')
    return categoryColors[key] || categoryColors.other
  })
}

// Format category label for display
function formatCategoryLabel(category: string): string {
  const labels: Record<string, string> = {
    thread_unsafe_singleton: 'Thread-Unsafe Singleton',
    unprotected_global_state: 'Unprotected Global State',
    unprotected_global_modification: 'Unprotected Global Modification',
    unprotected_subscript_assignment: 'Unprotected Subscript',
    unprotected_mutating_method: 'Unprotected Mutation',
    async_shared_state: 'Async Shared State',
    async_global_modification: 'Async Global Modification',
    file_write_without_lock: 'File Write Without Lock',
    file_writes_without_locking: 'File Writes Without Lock',
    read_modify_write: 'Read-Modify-Write',
    read_modify_write_pattern: 'Read-Modify-Write Pattern'
  }

  const key = category.toLowerCase().replace(/[^a-z_]/g, '_').replace(/__+/g, '_')
  if (labels[key]) return labels[key]

  // Convert snake_case to Title Case
  return category
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}
</script>
