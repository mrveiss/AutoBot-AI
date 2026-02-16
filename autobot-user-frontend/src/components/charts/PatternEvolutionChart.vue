<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  PatternEvolutionChart.vue - Anti-pattern evolution visualization (Issue #243)
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
import type { PatternEvolutionData } from '@/composables/useEvolution'

interface Props {
  data: PatternEvolutionData
  height?: number | string
  title?: string
  subtitle?: string
  loading?: boolean
  error?: string
}

const props = withDefaults(defineProps<Props>(), {
  height: 400,
  title: 'Pattern Evolution',
  subtitle: 'Anti-pattern occurrences over time',
  loading: false,
  error: '',
})

// Prepare series data for ApexCharts
const series = computed(() => {
  if (!props.data || Object.keys(props.data).length === 0) {
    return []
  }

  return Object.entries(props.data).map(([patternType, occurrences]) => ({
    name: formatPatternName(patternType),
    data: occurrences.map((point) => ({
      x: new Date(point.timestamp).getTime(),
      y: point.count,
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
    width: 2,
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
      text: 'Occurrences',
    },
    min: 0,
    labels: {
      formatter: (value: number) => Math.floor(value).toString(),
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
    markers: {
      width: 12,
      height: 12,
      radius: 2,
    },
  },
  grid: {
    borderColor: 'var(--color-border, #2d3748)',
    strokeDashArray: 4,
  },
  colors: [
    '#ef4444', // red - critical patterns
    '#f59e0b', // orange - warning patterns
    '#3b82f6', // blue - info patterns
    '#8b5cf6', // purple
    '#10b981', // green
    '#ec4899', // pink
  ],
  markers: {
    size: 4,
    hover: {
      size: 6,
    },
  },
}))

function formatPatternName(pattern: string): string {
  return pattern
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
