<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  EvolutionTimelineChart.vue - Timeline visualization for code evolution (Issue #243)
-->
<template>
  <BaseChart
    type="line"
    :height="height"
    :series="series"
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
import type { TimelineData } from '@/composables/useEvolution'

interface Props {
  data: TimelineData[]
  height?: number | string
  title?: string
  subtitle?: string
  loading?: boolean
  error?: string
  metrics?: string[]
}

const props = withDefaults(defineProps<Props>(), {
  height: 400,
  title: 'Code Quality Evolution',
  subtitle: 'Historical trends over time',
  loading: false,
  error: '',
  metrics: () => ['overall_score', 'maintainability', 'complexity'],
})

// Prepare series data for ApexCharts
const series = computed(() => {
  if (!props.data || props.data.length === 0) {
    return []
  }

  return props.metrics.map((metric) => ({
    name: formatMetricName(metric),
    data: props.data.map((point) => ({
      x: new Date(point.timestamp).getTime(),
      y: point[metric] || 0,
    })),
  }))
})

// Chart options
const chartOptions = computed<ApexOptions>(() => ({
  chart: {
    type: 'line',
    toolbar: {
      show: true,
      tools: {
        download: true,
        selection: true,
        zoom: true,
        zoomin: true,
        zoomout: true,
        pan: true,
        reset: true,
      },
    },
    zoom: {
      enabled: true,
    },
    animations: {
      enabled: true,
      easing: 'easeinout',
      speed: 800,
    },
  },
  stroke: {
    curve: 'smooth',
    width: 3,
  },
  xaxis: {
    type: 'datetime',
    labels: {
      datetimeUTC: false,
      format: 'MMM dd',
    },
  },
  yaxis: {
    title: {
      text: 'Score (0-100)',
    },
    min: 0,
    max: 100,
    labels: {
      formatter: (value: number) => value.toFixed(1),
    },
  },
  tooltip: {
    shared: true,
    intersect: false,
    x: {
      format: 'MMM dd, yyyy',
    },
  },
  legend: {
    position: 'top',
    horizontalAlign: 'left',
  },
  grid: {
    borderColor: 'var(--color-border, #2d3748)',
    strokeDashArray: 4,
  },
  colors: ['#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6'],
}))

function formatMetricName(metric: string): string {
  return metric
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}
</script>

<style scoped>
.base-chart {
  background: var(--bg-secondary);
  border-radius: 8px;
  padding: 1rem;
}
</style>
