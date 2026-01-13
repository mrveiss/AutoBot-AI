<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  ErrorComponentMap.vue - Component error heatmap/treemap visualization
  Part of Error Monitoring Dashboard (Issue #579)
-->
<template>
  <div class="error-component-map">
    <BaseChart
      v-if="hasData"
      type="treemap"
      :series="chartSeries"
      :options="chartOptions"
      :height="height"
    />
    <EmptyState
      v-else
      icon="fas fa-sitemap"
      message="No component data available"
      variant="info"
    />

    <!-- Most Problematic Components List -->
    <div v-if="mostProblematic.length > 0" class="problematic-list">
      <div class="problematic-header">
        <i class="fas fa-fire-alt"></i>
        Most Problematic Components
      </div>
      <div class="problematic-items">
        <div
          v-for="(item, index) in mostProblematic"
          :key="item[0]"
          class="problematic-item"
          :class="{ 'top-offender': index === 0 }"
        >
          <span class="rank">#{{ index + 1 }}</span>
          <span class="component-name">{{ item[0] }}</span>
          <span class="error-count">{{ item[1] }} errors</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import BaseChart from '@/components/charts/BaseChart.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import type { ApexOptions } from 'apexcharts'

interface ComponentData {
  components: Record<string, number>
  most_problematic: Array<[string, number]>
}

interface Props {
  data: ComponentData
  height?: number | string
}

const props = withDefaults(defineProps<Props>(), {
  data: () => ({
    components: {},
    most_problematic: []
  }),
  height: 300
})

const hasData = computed(() => {
  return Object.keys(props.data.components || {}).length > 0
})

const mostProblematic = computed(() => {
  return props.data.most_problematic || []
})

const chartSeries = computed(() => {
  const components = props.data.components || {}
  const data = Object.entries(components).map(([name, count]) => ({
    x: name,
    y: count
  }))

  return [{
    data
  }]
})

const chartOptions = computed<ApexOptions>(() => {
  return {
    legend: {
      show: false
    },
    plotOptions: {
      treemap: {
        enableShades: true,
        shadeIntensity: 0.5,
        distributed: true,
        colorScale: {
          ranges: [
            { from: 0, to: 5, color: '#22c55e', name: 'Low' },
            { from: 6, to: 15, color: '#f59e0b', name: 'Medium' },
            { from: 16, to: 30, color: '#f97316', name: 'High' },
            { from: 31, to: 1000, color: '#ef4444', name: 'Critical' }
          ]
        }
      }
    },
    dataLabels: {
      enabled: true,
      style: {
        fontSize: '12px'
      },
      formatter: (_text: string, op: { value: number }) => {
        return `${op.value}`
      },
      offsetY: -4
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
            height: 200
          },
          dataLabels: {
            style: {
              fontSize: '10px'
            }
          }
        }
      }
    ]
  }
})
</script>

<style scoped>
.error-component-map {
  width: 100%;
}

.problematic-list {
  margin-top: var(--spacing-4);
  padding-top: var(--spacing-4);
  border-top: 1px solid var(--border-default);
}

.problematic-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin-bottom: var(--spacing-3);
}

.problematic-header i {
  color: var(--chart-orange);
}

.problematic-items {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.problematic-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  transition: background var(--duration-150) var(--ease-in-out);
}

.problematic-item:hover {
  background: var(--bg-tertiary);
}

.problematic-item.top-offender {
  background: var(--color-error-bg);
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.problematic-item.top-offender:hover {
  background: rgba(239, 68, 68, 0.2);
}

.rank {
  font-weight: var(--font-bold);
  color: var(--text-tertiary);
  min-width: 24px;
}

.top-offender .rank {
  color: var(--color-error);
}

.component-name {
  flex: 1;
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
}

.error-count {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  background: var(--bg-tertiary);
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-sm);
}

.top-offender .error-count {
  background: var(--color-error);
  color: var(--text-on-error);
}
</style>
