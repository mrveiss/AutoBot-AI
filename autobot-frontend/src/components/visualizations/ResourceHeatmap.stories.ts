// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import type { Meta, StoryObj } from '@storybook/vue3'
import ResourceHeatmap from './ResourceHeatmap.vue'

const meta = {
  title: 'Components/Visualizations/ResourceHeatmap',
  component: ResourceHeatmap,
  tags: ['autodocs'],
  argTypes: {
    title: {
      control: 'text',
      description: 'Override the default panel title',
    },
    height: {
      control: 'number',
      description: 'Chart height in pixels',
    },
    refreshInterval: {
      control: 'number',
      description: 'Polling interval in milliseconds (0 = disabled)',
    },
    machine: {
      control: 'select',
      options: ['all', 'main-vm', 'frontend-vm', 'browser-vm'],
      description: 'Filter metrics to a specific machine or show all',
    },
  },
} as Meta<typeof ResourceHeatmap>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const Default: Story = {
  args: {
    height: 350,
    refreshInterval: 0,
    machine: 'all',
  },
}

export const WithCustomTitle: Story = {
  args: {
    title: 'CPU Usage Heatmap',
    height: 350,
    refreshInterval: 0,
    machine: 'all',
  },
}

export const TallChart: Story = {
  name: 'Tall Chart (500px)',
  args: {
    height: 500,
    refreshInterval: 0,
    machine: 'all',
  },
}

export const SingleMachine: Story = {
  name: 'Single Machine Filter',
  args: {
    title: 'Main VM Resources',
    height: 350,
    refreshInterval: 0,
    machine: 'main-vm',
  },
}

export const LivePolling: Story = {
  args: {
    title: 'Live Resource Heatmap',
    height: 350,
    refreshInterval: 60000,
    machine: 'all',
  },
}
