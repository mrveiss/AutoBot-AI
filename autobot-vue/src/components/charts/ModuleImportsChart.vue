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
  colors: ['#8b5cf6'],
  xaxis: {
    categories: sortedData.value.map((item) => truncatePath(item.path)),
    title: {
      text: 'Number of Imports',
      style: {
        fontSize: '12px',
        color: '#94a3b8'
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
  tooltip: {
    custom: ({ dataPointIndex }: { dataPointIndex: number }) => {
      const item = sortedData.value[dataPointIndex]
      if (!item) return ''

      return `
        <div style="background: #1e293b; border: 1px solid #475569; border-radius: 6px; padding: 12px; max-width: 350px;">
          <div style="font-weight: 600; color: #e2e8f0; margin-bottom: 8px; word-break: break-all;">
            ${item.path}
          </div>
          <div style="color: #94a3b8; display: flex; flex-direction: column; gap: 4px;">
            <div><span style="color: #8b5cf6; font-weight: 600;">${item.import_count}</span> imports</div>
            <div><span style="color: #10b981;">${item.functions}</span> functions</div>
            <div><span style="color: #f59e0b;">${item.classes}</span> classes</div>
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
