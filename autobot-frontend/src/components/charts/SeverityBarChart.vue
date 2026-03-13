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
    :title="title ?? $t('charts.severity.title')"
    :subtitle="subtitle"
    :loading="loading"
    :error="error"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import BaseChart from './BaseChart.vue'
import { getCssVar, getSeverityColors } from '@/composables/useCssVars'
import type { ApexOptions } from 'apexcharts'

const { t } = useI18n()

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
  title: undefined,
  subtitle: '',
  height: 300,
  loading: false,
  error: ''
})

// Transform data for bar chart - support both count/value and severity/name formats
const chartSeries = computed(() => [
  {
    name: t('charts.severity.seriesName'),
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
      formatter: (value: number) => t('charts.severity.tooltipProblems', { count: value.toLocaleString() })
    }
  },
  legend: {
    show: false
  }
}))


// Format severity label for display
function formatSeverityLabel(severity: string): string {
  const labels: Record<string, string> = {
    critical: t('charts.severity.levels.critical'),
    high: t('charts.severity.levels.high'),
    error: t('charts.severity.levels.error'),
    medium: t('charts.severity.levels.medium'),
    warning: t('charts.severity.levels.warning'),
    low: t('charts.severity.levels.low'),
    info: t('charts.severity.levels.info'),
    hint: t('charts.severity.levels.hint'),
    suggestion: t('charts.severity.levels.suggestion'),
    trivial: t('charts.severity.levels.trivial')
  }

  return labels[severity.toLowerCase()] || severity.charAt(0).toUpperCase() + severity.slice(1)
}
</script>
