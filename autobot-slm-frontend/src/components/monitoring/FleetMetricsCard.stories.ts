// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import type { Meta } from '@storybook/vue3'
import type { FleetMetricsDetailed } from '@/composables/usePrometheusMetrics'
import FleetMetricsCard from './FleetMetricsCard.vue'

const sampleMetrics: FleetMetricsDetailed = {
  total_nodes: 5,
  online_nodes: 4,
  degraded_nodes: 1,
  offline_nodes: 0,
  avg_cpu_percent: 42.3,
  avg_memory_percent: 68.1,
  avg_disk_percent: 31.7,
  total_services: 25,
  running_services: 23,
  failed_services: 1,
  nodes: [],
  timestamp: new Date().toISOString(),
}

const meta = {
  title: 'Monitoring/FleetMetricsCard',
  component: FleetMetricsCard,
  tags: ['autodocs'],
  argTypes: {
    loading: { control: 'boolean' },
  },
} satisfies Meta<typeof FleetMetricsCard>

export default meta

export const WithMetrics = {
  args: {
    metrics: sampleMetrics,
    loading: false,
  },
}

export const Loading = {
  args: {
    metrics: null,
    loading: true,
  },
}

export const NoData = {
  args: {
    metrics: null,
    loading: false,
  },
}

export const HighLoad = {
  args: {
    metrics: {
      ...sampleMetrics,
      avg_cpu_percent: 93.5,
      avg_memory_percent: 91.2,
      online_nodes: 2,
    },
    loading: false,
  },
}
