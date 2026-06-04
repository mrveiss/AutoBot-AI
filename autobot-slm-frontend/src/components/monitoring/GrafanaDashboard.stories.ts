// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import type { Meta } from '@storybook/vue3'
import GrafanaDashboard from './GrafanaDashboard.vue'

const meta = {
  title: 'Monitoring/GrafanaDashboard',
  component: GrafanaDashboard,
  tags: ['autodocs'],
  argTypes: {
    dashboard: {
      control: { type: 'select' },
      options: ['overview', 'system', 'performance', 'nodes', 'redis', 'api-health'],
    },
    theme: { control: { type: 'select' }, options: ['light', 'dark'] },
    timeRange: { control: 'text' },
    refresh: { control: 'text' },
    showControls: { control: 'boolean' },
  },
} satisfies Meta<typeof GrafanaDashboard>

export default meta

export const Overview = {
  args: {
    dashboard: 'overview',
    timeRange: 'now-1h',
    theme: 'light',
    refresh: '30s',
    width: '100%',
    height: 500,
    showControls: true,
  },
}

export const SystemDark = {
  args: {
    dashboard: 'system',
    timeRange: 'now-6h',
    theme: 'dark',
    refresh: '1m',
    width: '100%',
    height: 500,
    showControls: false,
  },
}

export const NodeMetrics = {
  args: {
    dashboard: 'nodes',
    timeRange: 'now-24h',
    theme: 'light',
    refresh: '5m',
    width: '100%',
    height: 600,
    showControls: true,
  },
}
