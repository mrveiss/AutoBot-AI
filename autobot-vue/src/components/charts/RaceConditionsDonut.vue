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

interface RaceConditionData {
  category: string
  count: number
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

// Transform data for donut chart
const chartSeries = computed(() => {
  return props.data.map((item) => item.count)
})

const totalCount = computed(() => {
  return props.data.reduce((sum, item) => sum + item.count, 0)
})

const chartOptions = computed<ApexOptions>(() => ({
  labels: props.data.map((item) => formatCategoryLabel(item.category)),
  colors: getCategoryColors(props.data.map((item) => item.category)),
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
      const count = props.data[opts.seriesIndex]?.count || 0
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
            color: '#e2e8f0'
          },
          value: {
            show: true,
            fontSize: '24px',
            color: '#e2e8f0',
            formatter: () => totalCount.value.toString()
          },
          total: {
            show: true,
            showAlways: true,
            label: 'Total Issues',
            fontSize: '12px',
            color: '#94a3b8',
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
function getCategoryColors(categories: string[]): string[] {
  const categoryColors: Record<string, string> = {
    // Thread safety issues
    thread_unsafe_singleton: '#ef4444',
    unprotected_global_state: '#f97316',
    unprotected_global_modification: '#f97316',
    unprotected_subscript_assignment: '#f59e0b',
    unprotected_mutating_method: '#eab308',

    // Async issues
    async_shared_state: '#8b5cf6',
    async_global_modification: '#a855f7',

    // File operations
    file_write_without_lock: '#06b6d4',
    file_writes_without_locking: '#06b6d4',

    // Read-modify-write
    read_modify_write: '#ec4899',
    read_modify_write_pattern: '#ec4899',

    // Default
    other: '#6366f1'
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
