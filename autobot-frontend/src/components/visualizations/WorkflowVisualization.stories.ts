// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import type { Meta, StoryObj } from '@storybook/vue3'
import WorkflowVisualization from './WorkflowVisualization.vue'

const meta = {
  title: 'Components/Visualizations/WorkflowVisualization',
  component: WorkflowVisualization,
  tags: ['autodocs'],
  argTypes: {
    layoutMode: {
      control: 'select',
      options: ['horizontal', 'vertical'],
      description: 'Initial node layout direction',
    },
    workflow: {
      control: 'object',
      description: 'Workflow data (nodes + connections). Omit to use built-in sample data.',
    },
  },
} as Meta<typeof WorkflowVisualization>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const SampleData: Story = {
  name: 'Sample Data (No Props)',
  args: {
    layoutMode: 'horizontal',
  },
}

export const HorizontalLayout: Story = {
  args: {
    layoutMode: 'horizontal',
  },
}

export const VerticalLayout: Story = {
  args: {
    layoutMode: 'vertical',
  },
}

const completedWorkflow = {
  id: 'wf-demo-001',
  name: 'Data Pipeline — Completed',
  status: 'completed' as const,
  nodes: [
    { id: 'start', name: 'Start', type: 'start' as const, status: 'completed' as const, x: 100, y: 150 },
    { id: 'fetch', name: 'Fetch Data', type: 'action' as const, status: 'completed' as const, x: 280, y: 150, duration: 2300 },
    { id: 'validate', name: 'Validate', type: 'decision' as const, status: 'completed' as const, x: 460, y: 150, duration: 310 },
    { id: 'transform', name: 'Transform', type: 'task' as const, status: 'completed' as const, x: 640, y: 80, duration: 5100 },
    { id: 'store', name: 'Store Result', type: 'action' as const, status: 'completed' as const, x: 820, y: 150, duration: 780 },
    { id: 'end', name: 'End', type: 'end' as const, status: 'completed' as const, x: 1000, y: 150 },
  ],
  connections: [
    { from: 'start', to: 'fetch', status: 'success' as const },
    { from: 'fetch', to: 'validate', status: 'success' as const },
    { from: 'validate', to: 'transform', status: 'success' as const, label: 'valid' },
    { from: 'transform', to: 'store', status: 'success' as const },
    { from: 'store', to: 'end', status: 'success' as const },
  ],
}

export const CompletedWorkflow: Story = {
  name: 'Completed Workflow',
  args: {
    workflow: completedWorkflow,
    layoutMode: 'horizontal',
  },
}

const runningWorkflow = {
  id: 'wf-demo-002',
  name: 'Model Training — Running',
  status: 'running' as const,
  nodes: [
    { id: 'start', name: 'Start', type: 'start' as const, status: 'completed' as const, x: 100, y: 150 },
    { id: 'prep', name: 'Prepare Data', type: 'action' as const, status: 'completed' as const, x: 280, y: 150, duration: 4500 },
    { id: 'train', name: 'Train Model', type: 'task' as const, status: 'running' as const, x: 460, y: 150 },
    { id: 'eval', name: 'Evaluate', type: 'action' as const, status: 'pending' as const, x: 640, y: 150 },
    { id: 'end', name: 'End', type: 'end' as const, status: 'pending' as const, x: 820, y: 150 },
  ],
  connections: [
    { from: 'start', to: 'prep', status: 'success' as const },
    { from: 'prep', to: 'train', status: 'active' as const },
    { from: 'train', to: 'eval' },
    { from: 'eval', to: 'end' },
  ],
}

export const RunningWorkflow: Story = {
  name: 'Running Workflow',
  args: {
    workflow: runningWorkflow,
    layoutMode: 'horizontal',
  },
}

const failedWorkflow = {
  id: 'wf-demo-003',
  name: 'Deployment Pipeline — Failed',
  status: 'failed' as const,
  nodes: [
    { id: 'start', name: 'Start', type: 'start' as const, status: 'completed' as const, x: 100, y: 150 },
    { id: 'build', name: 'Build Image', type: 'action' as const, status: 'completed' as const, x: 280, y: 150, duration: 18000 },
    { id: 'test', name: 'Run Tests', type: 'task' as const, status: 'failed' as const, x: 460, y: 150, duration: 3200, error: 'Test suite failed: 3 assertions failed in auth module' },
    { id: 'deploy', name: 'Deploy', type: 'action' as const, status: 'skipped' as const, x: 640, y: 150 },
    { id: 'end', name: 'End', type: 'end' as const, status: 'pending' as const, x: 820, y: 150 },
  ],
  connections: [
    { from: 'start', to: 'build', status: 'success' as const },
    { from: 'build', to: 'test', status: 'success' as const },
    { from: 'test', to: 'deploy', status: 'error' as const },
    { from: 'deploy', to: 'end' },
  ],
}

export const FailedWorkflow: Story = {
  name: 'Failed Workflow',
  args: {
    workflow: failedWorkflow,
    layoutMode: 'horizontal',
  },
}
