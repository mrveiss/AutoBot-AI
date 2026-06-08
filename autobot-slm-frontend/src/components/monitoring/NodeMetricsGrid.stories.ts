// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import type { Meta } from '@storybook/vue3'
import type { NodeMetricsDetailed } from '@/composables/usePrometheusMetrics'
import NodeMetricsGrid from './NodeMetricsGrid.vue'

const sampleNodes: NodeMetricsDetailed[] = [
  {
    node_id: 'node-01',
    hostname: 'prod-01.autobot.internal',
    ip_address: '192.168.1.10',
    status: 'online',
    cpu_percent: 38.4,
    memory_percent: 62.1,
    disk_percent: 28.5,
    last_heartbeat: new Date().toISOString(),
    services_running: 12,
    services_failed: 0,
  },
  {
    node_id: 'node-02',
    hostname: 'prod-02.autobot.internal',
    ip_address: '192.168.1.11',
    status: 'degraded',
    cpu_percent: 87.9,
    memory_percent: 91.3,
    disk_percent: 45.2,
    last_heartbeat: new Date(Date.now() - 60000).toISOString(),
    services_running: 9,
    services_failed: 1,
  },
]

const meta = {
  title: 'Monitoring/NodeMetricsGrid',
  component: NodeMetricsGrid,
  tags: ['autodocs'],
  argTypes: {
    loading: { control: 'boolean' },
  },
} satisfies Meta<typeof NodeMetricsGrid>

export default meta

export const WithNodes = {
  args: { nodes: sampleNodes, loading: false },
}

export const Loading = {
  args: { nodes: [], loading: true },
}

export const Empty = {
  args: { nodes: [], loading: false },
}
