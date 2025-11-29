<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  DependencyTreemap.vue - Treemap visualization for external dependencies
-->
<template>
  <BaseChart
    type="treemap"
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

interface DependencyData {
  package: string
  usage_count: number
}

interface Props {
  data: DependencyData[]
  title?: string
  subtitle?: string
  height?: number | string
  loading?: boolean
  error?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: 'External Dependencies',
  subtitle: 'Package usage across codebase',
  height: 400,
  loading: false,
  error: ''
})

// Transform data for treemap
const chartSeries = computed(() => [
  {
    data: props.data.map((item) => ({
      x: item.package,
      y: item.usage_count
    }))
  }
])

const chartOptions = computed<ApexOptions>(() => ({
  chart: {
    type: 'treemap'
  },
  legend: {
    show: false
  },
  colors: [
    '#3b82f6',
    '#10b981',
    '#f59e0b',
    '#8b5cf6',
    '#06b6d4',
    '#ec4899',
    '#f97316',
    '#84cc16',
    '#6366f1',
    '#14b8a6'
  ],
  plotOptions: {
    treemap: {
      distributed: true,
      enableShades: true,
      shadeIntensity: 0.3,
      colorScale: {
        ranges: [
          { from: 0, to: 10, color: '#3b82f6' },
          { from: 11, to: 25, color: '#10b981' },
          { from: 26, to: 50, color: '#f59e0b' },
          { from: 51, to: 100, color: '#ef4444' }
        ]
      }
    }
  },
  dataLabels: {
    enabled: true,
    style: {
      fontSize: '12px',
      fontWeight: 600
    },
    formatter: (text: string, op: { value: number }) => {
      return `${text}\n${op.value} uses`
    },
    offsetY: -4
  },
  tooltip: {
    y: {
      formatter: (value: number) => `${value} imports across codebase`
    }
  }
}))
</script>
