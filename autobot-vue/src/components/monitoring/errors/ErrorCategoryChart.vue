<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  ErrorCategoryChart.vue - Category breakdown pie/donut chart
  Part of Error Monitoring Dashboard (Issue #579)
-->
<template>
  <div class="error-category-chart">
    <BaseChart
      v-if="hasData"
      type="donut"
      :series="chartSeries"
      :options="chartOptions"
      :height="height"
    />
    <EmptyState
      v-else
      icon="fas fa-chart-pie"
      message="No category data available"
      variant="info"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import BaseChart from '@/components/charts/BaseChart.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import type { ApexOptions } from 'apexcharts'

interface CategoryData {
  [category: string]: {
    count: number
    percentage: number
  }
}

interface Props {
  categories: CategoryData
  height?: number | string
}

const props = withDefaults(defineProps<Props>(), {
  categories: () => ({}),
  height: 300
})

const hasData = computed(() => {
  return Object.keys(props.categories).length > 0
})

const chartSeries = computed(() => {
  return Object.values(props.categories).map(cat => cat.count)
})

const chartOptions = computed<ApexOptions>(() => {
  const labels = Object.keys(props.categories).map(cat => {
    // Format category names nicely
    return cat.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
  })

  return {
    labels,
    legend: {
      show: true,
      position: 'bottom',
      horizontalAlign: 'center'
    },
    plotOptions: {
      pie: {
        donut: {
          size: '60%',
          labels: {
            show: true,
            name: {
              show: true,
              fontSize: '14px'
            },
            value: {
              show: true,
              fontSize: '20px',
              formatter: (val: string) => val
            },
            total: {
              show: true,
              showAlways: true,
              label: 'Total Errors',
              fontSize: '12px',
              formatter: (w) => {
                return w.globals.seriesTotals.reduce((a: number, b: number) => a + b, 0).toString()
              }
            }
          }
        }
      }
    },
    dataLabels: {
      enabled: true,
      formatter: (_val: number, opts: { seriesIndex: number; w: { config: { series: number[] } } }) => {
        const series = opts.w.config.series
        const total = series.reduce((a: number, b: number) => a + b, 0)
        const value = series[opts.seriesIndex]
        const percentage = total > 0 ? ((value / total) * 100).toFixed(1) : '0'
        return `${percentage}%`
      }
    },
    tooltip: {
      y: {
        formatter: (val: number) => `${val} errors`
      }
    },
    responsive: [
      {
        breakpoint: 480,
        options: {
          chart: {
            height: 250
          },
          legend: {
            position: 'bottom'
          }
        }
      }
    ]
  }
})
</script>

<style scoped>
.error-category-chart {
  width: 100%;
  min-height: 250px;
}
</style>
