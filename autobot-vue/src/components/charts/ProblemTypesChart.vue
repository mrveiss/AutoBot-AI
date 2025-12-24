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

// Get colors based on problem types
function getColorForTypes(types: string[]): string[] {
  const typeColors: Record<string, string> = {
    // Severity-based
    error: '#ef4444',
    warning: '#f59e0b',
    info: '#3b82f6',
    hint: '#10b981',

    // Category-based
    security: '#ef4444',
    race_condition: '#f97316',
    performance: '#f59e0b',
    style: '#8b5cf6',
    complexity: '#ec4899',
    unused: '#64748b',
    deprecated: '#94a3b8',
    type_error: '#06b6d4',
    syntax: '#ef4444',
    logic: '#f59e0b',
    documentation: '#3b82f6',
    maintainability: '#10b981',
    best_practice: '#84cc16',

    // Default
    other: '#6366f1'
  }

  return types.map((type) => {
    const key = type.toLowerCase().replace(/[^a-z_]/g, '_')
    return typeColors[key] || typeColors.other
  })
}
</script>
