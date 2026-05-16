// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import type { Meta, StoryObj } from '@storybook/vue3'
import AgentActivityVisualization from './AgentActivityVisualization.vue'

const meta = {
  title: 'Components/Visualizations/AgentActivityVisualization',
  component: AgentActivityVisualization,
  tags: ['autodocs'],
  argTypes: {
    title: {
      control: 'text',
      description: 'Override the default panel title',
    },
    refreshInterval: {
      control: 'number',
      description: 'Polling interval in milliseconds (0 = disabled)',
    },
  },
} as Meta<typeof AgentActivityVisualization>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const Default: Story = {
  args: {
    refreshInterval: 0,
  },
}

export const WithCustomTitle: Story = {
  args: {
    title: 'Production Agent Fleet',
    refreshInterval: 0,
  },
}

export const LivePolling: Story = {
  args: {
    title: 'Live Agent Activity',
    refreshInterval: 5000,
  },
}

export const GridView: Story = {
  name: 'Grid View (Default)',
  args: {
    title: 'Agent Grid',
    refreshInterval: 0,
  },
}

export const NoAutoRefresh: Story = {
  name: 'Static — No Auto Refresh',
  args: {
    title: 'Static Agent View',
    refreshInterval: 0,
  },
}
