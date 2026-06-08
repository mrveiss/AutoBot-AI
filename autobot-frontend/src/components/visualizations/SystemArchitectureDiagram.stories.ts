// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import type { Meta, StoryObj } from '@storybook/vue3'
import SystemArchitectureDiagram from './SystemArchitectureDiagram.vue'

const meta = {
  title: 'Components/Visualizations/SystemArchitectureDiagram',
  component: SystemArchitectureDiagram,
  tags: ['autodocs'],
  argTypes: {
    title: {
      control: 'text',
      description: 'Override the default diagram title',
    },
    height: {
      control: 'number',
      description: 'Diagram canvas height in pixels',
    },
    autoRefresh: {
      control: 'boolean',
      description: 'Automatically refresh service health at the given interval',
    },
    refreshInterval: {
      control: 'number',
      description: 'Health refresh interval in milliseconds',
    },
  },
} as Meta<typeof SystemArchitectureDiagram>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const Default: Story = {
  args: {
    height: 600,
    autoRefresh: false,
  },
}

export const WithCustomTitle: Story = {
  args: {
    title: 'AutoBot Production Architecture',
    height: 600,
    autoRefresh: false,
  },
}

export const Compact: Story = {
  name: 'Compact (400px)',
  args: {
    height: 400,
    autoRefresh: false,
  },
}

export const WithAutoRefresh: Story = {
  name: 'Auto-Refresh Enabled',
  args: {
    title: 'Live Architecture',
    height: 600,
    autoRefresh: true,
    refreshInterval: 30000,
  },
}

export const Tall: Story = {
  name: 'Tall Canvas (800px)',
  args: {
    height: 800,
    autoRefresh: false,
  },
}
