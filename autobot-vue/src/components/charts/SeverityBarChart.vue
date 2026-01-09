<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  SeverityBarChart.vue - Horizontal bar chart for problem severity levels
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

interface SeverityData {
  severity?: string
  name?: string
  count?: number
  value?: number
}

interface Props {
  data: SeverityData[]
  title?: string
  subtitle?: string
  height?: number | string
  loading?: boolean
  error?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: 'Problems by Severity',
  subtitle: '',
  height: 300,
  loading: false,
  error: ''
})

// Transform data for bar chart - support both count/value and severity/name formats
const chartSeries = computed(() => [
  {
    name: 'Problems',
    data: props.data.map((item) => item.count ?? item.value ?? 0)
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
      barHeight: '60%',
      distributed: true,
      dataLabels: {
        position: 'center'
      }
    }
  },
  colors: getSeverityColors(props.data.map((item) => item.severity ?? item.name ?? 'unknown')),
  xaxis: {
    categories: props.data.map((item) => formatSeverityLabel(item.severity ?? item.name ?? 'unknown')),
    labels: {
      formatter: (value: string) => {
        const num = parseInt(value)
        if (num >= 1000) return `${(num / 1000).toFixed(1)}k`
        return value
      }
    }
  },
  yaxis: {
    labels: {
      style: {
        fontSize: '13px',
        fontWeight: 500
      }
    }
  },
  dataLabels: {
    enabled: true,
    formatter: (value: number) => value.toLocaleString(),
    style: {
      fontSize: '12px',
      fontWeight: 600
    },
    offsetX: 0
  },
  tooltip: {
    y: {
      formatter: (value: number) => `${value.toLocaleString()} problems`
    }
  },
  legend: {
    show: false
  }
}))

// Get colors based on severity
// Issue #704: Using design tokens with fallbacks for SSR compatibility
function getSeverityColors(severities: string[]): string[] {
  const severityColors: Record<string, string> = {
    critical: getCssVar('--color-error-hover', '#dc2626'),
    high: getCssVar('--color-error', '#ef4444'),
    error: getCssVar('--color-error', '#ef4444'),
    medium: getCssVar('--color-warning', '#f59e0b'),
    warning: getCssVar('--color-warning', '#f59e0b'),
    low: getCssVar('--color-info', '#3b82f6'),
    info: getCssVar('--color-info', '#3b82f6'),
    hint: getCssVar('--color-success', '#10b981'),
    suggestion: getCssVar('--color-success', '#10b981'),
    trivial: getCssVar('--text-tertiary', '#64748b')
  }

  return severities.map((severity) => {
    const key = severity.toLowerCase()
    return severityColors[key] || getCssVar('--chart-indigo', '#6366f1')
  })
}

// Format severity label for display
function formatSeverityLabel(severity: string): string {
  const labels: Record<string, string> = {
    critical: 'Critical',
    high: 'High',
    error: 'Error',
    medium: 'Medium',
    warning: 'Warning',
    low: 'Low',
    info: 'Info',
    hint: 'Hint',
    suggestion: 'Suggestion',
    trivial: 'Trivial'
  }

  return labels[severity.toLowerCase()] || severity.charAt(0).toUpperCase() + severity.slice(1)
}
</script>
