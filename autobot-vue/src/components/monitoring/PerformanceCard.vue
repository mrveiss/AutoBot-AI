<template>
  <BasePanel variant="elevated" size="small">
    <template #header>
      <h5>
        <i :class="icon"></i>
        {{ title }}
      </h5>
    </template>

    <div v-if="hasMetrics" class="metrics-content">
      <div v-for="metric in metrics" :key="metric.label" class="metric-row">
        <span>{{ metric.label }}</span>
        <span class="metric-value">{{ metric.value }}</span>
      </div>
    </div>

    <EmptyState
      v-else
      :icon="icon"
      :message="emptyMessage"
      compact
    />
  </BasePanel>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Performance Card Component
 *
 * Displays performance metrics in a card format.
 * Extracted from MonitoringDashboard.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import { computed } from 'vue'
import BasePanel from '@/components/base/BasePanel.vue'
import EmptyState from '@/components/ui/EmptyState.vue'

interface Metric {
  label: string
  value: string
}

interface Props {
  title: string
  icon: string
  metrics: Metric[]
  emptyMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
  emptyMessage: 'Data not available'
})

const hasMetrics = computed(() => props.metrics.length > 0)
</script>

<style scoped>
.metrics-content {
  padding: 10px 0;
}

.metric-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 0.9em;
}

.metric-value {
  font-weight: 600;
  color: #333;
}
</style>
