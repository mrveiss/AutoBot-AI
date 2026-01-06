<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  TopFilesChart.vue - Horizontal bar chart for files with most problems
-->
<template>
  <BaseChart
    type="bar"
    :height="height"
    :series="chartSeries"
    :options="(chartOptions as any)"
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

interface FileData {
  file?: string
  name?: string
  count?: number
  value?: number
  severity?: string
}

interface Props {
  data: FileData[]
  title?: string
  subtitle?: string
  height?: number | string
  maxFiles?: number
  loading?: boolean
  error?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: 'Top Files with Most Problems',
  subtitle: '',
  height: 400,
  maxFiles: 10,
  loading: false,
  error: ''
})

// Sort and limit data - support both count/value and file/name formats
const sortedData = computed(() => {
  return [...props.data]
    .sort((a, b) => (b.count ?? b.value ?? 0) - (a.count ?? a.value ?? 0))
    .slice(0, props.maxFiles)
})

// Transform data for bar chart
const chartSeries = computed(() => [
  {
    name: 'Problems',
    data: sortedData.value.map((item) => item.count ?? item.value ?? 0)
  }
])

const chartOptions = computed(() => ({
  chart: {
    type: 'bar'
  },
  plotOptions: {
    bar: {
      horizontal: true,
      borderRadius: 4,
      barHeight: '70%',
      distributed: false,
      dataLabels: {
        position: 'center'
      }
    }
  },
  colors: ['#3b82f6'],
  xaxis: {
    categories: sortedData.value.map((item) => truncateFilePath(item.file ?? item.name ?? '')),
    labels: {
      formatter: (value: string) => {
        const num = parseInt(value)
        if (num >= 1000) return `${(num / 1000).toFixed(1)}k`
        return value
      }
    },
    title: {
      text: 'Number of Problems',
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
      maxWidth: 250,
      formatter: (value: string) => truncateFilePath(String(value), 40)
    }
  },
  dataLabels: {
    enabled: true,
    formatter: (value: number) => value.toLocaleString(),
    style: {
      fontSize: '11px',
      fontWeight: 600,
      colors: ['#fff']
    },
    offsetX: 0
  },
  tooltip: {
    custom: ({ dataPointIndex }: { dataPointIndex: number }) => {
      const item = sortedData.value[dataPointIndex]
      if (!item) return ''
      const filePath = item.file ?? item.name ?? 'Unknown'
      const problemCount = item.count ?? item.value ?? 0

      return `
        <div style="background: #1e293b; border: 1px solid #475569; border-radius: 6px; padding: 12px; max-width: 400px;">
          <div style="font-weight: 600; color: #e2e8f0; margin-bottom: 8px; word-break: break-all;">
            ${filePath}
          </div>
          <div style="color: #94a3b8;">
            <span style="color: #3b82f6; font-weight: 600;">${problemCount.toLocaleString()}</span> problems
          </div>
        </div>
      `
    }
  },
  legend: {
    show: false
  },
  grid: {
    xaxis: {
      lines: {
        show: true
      }
    },
    yaxis: {
      lines: {
        show: false
      }
    }
  }
}))

// Truncate file path for display
function truncateFilePath(path: string, maxLength: number = 35): string {
  if (!path) return ''
  if (path.length <= maxLength) return path

  // Get filename
  const parts = path.split('/')
  const filename = parts[parts.length - 1]

  // If filename alone is longer than max, truncate it
  if (filename.length >= maxLength - 3) {
    return '...' + filename.slice(-(maxLength - 3))
  }

  // Try to keep some path context
  const remaining = maxLength - filename.length - 4 // 4 for ".../""
  if (remaining > 0 && parts.length > 1) {
    const parentPath = parts.slice(0, -1).join('/')
    if (parentPath.length > remaining) {
      return '...' + parentPath.slice(-remaining) + '/' + filename
    }
    return path
  }

  return '.../' + filename
}
</script>
