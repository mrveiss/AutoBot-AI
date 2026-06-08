// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import WorkflowLiveDashboard from './WorkflowLiveDashboard.vue';

const meta = {
  title: 'Components/Workflow/WorkflowLiveDashboard',
  component: WorkflowLiveDashboard,
  tags: ['autodocs'],
  argTypes: {
    activeWorkflows: {
      control: 'object',
      description: 'Array of currently active workflow objects',
    },
    agentPerformance: {
      control: 'object',
      description: 'Record of agent performance data keyed by agent name',
    },
    agentCapabilities: {
      control: 'object',
      description: 'Record of agent capability data keyed by agent name',
    },
    loading: {
      control: 'boolean',
      description: 'Whether active workflows are loading',
    },
    loadingCapabilities: {
      control: 'boolean',
      description: 'Whether agent capabilities are loading',
    },
  },
} as Meta<typeof WorkflowLiveDashboard>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

const makeSteps = (statuses: string[]) =>
  statuses.map((status, i) => ({
    step_id: `step_${i}`,
    status,
    description: `Step ${i + 1}`,
    command: `cmd_${i}`,
    risk_level: 'low',
    requires_confirmation: false,
  }));

const runningWorkflow = {
  workflow_id: 'wf-live-001',
  name: 'CI/CD Pipeline',
  description: 'Continuous integration and deployment',
  automation_mode: 'full_auto',
  current_step: 2,
  total_steps: 6,
  steps: makeSteps(['completed', 'completed', 'executing', 'pending', 'pending', 'pending']),
  created_at: new Date(Date.now() - 900_000).toISOString(),
  started_at: new Date(Date.now() - 850_000).toISOString(),
  completed_at: null,
  is_paused: false,
  is_cancelled: false,
  automation_mode_label: 'Full Auto',
  phase: 'executing',
  active_service: 'autobot-backend',
};

const pausedWorkflow = {
  workflow_id: 'wf-live-002',
  name: 'Database Backup',
  description: 'Nightly database backup routine',
  automation_mode: 'supervised',
  current_step: 1,
  total_steps: 4,
  steps: makeSteps(['completed', 'paused', 'pending', 'pending']),
  created_at: new Date(Date.now() - 1_800_000).toISOString(),
  started_at: new Date(Date.now() - 1_750_000).toISOString(),
  completed_at: null,
  is_paused: true,
  is_cancelled: false,
  phase: 'executing',
  active_service: null,
};

const agentPerf = {
  coordinator: {
    agent_name: 'Coordinator',
    total_tasks: 20,
    successful_tasks: 19,
    failed_tasks: 1,
    average_duration: 8.4,
    reliability_score: 0.95,
  },
};

const agentCaps = {
  coordinator: {
    agent: 'Coordinator',
    capabilities: ['routing', 'scheduling'],
    performance: { total_tasks: 20, reliability: 0.95 },
  },
};

export const WithActiveWorkflows: Story = {
  args: {
    activeWorkflows: [runningWorkflow, pausedWorkflow],
    agentPerformance: agentPerf,
    agentCapabilities: agentCaps,
    loading: false,
    loadingCapabilities: false,
  },
};

export const Empty: Story = {
  args: {
    activeWorkflows: [],
    agentPerformance: {},
    agentCapabilities: {},
    loading: false,
    loadingCapabilities: false,
  },
};

export const Loading: Story = {
  args: {
    activeWorkflows: [],
    agentPerformance: {},
    agentCapabilities: {},
    loading: true,
    loadingCapabilities: true,
  },
};

export const SingleRunning: Story = {
  args: {
    activeWorkflows: [runningWorkflow],
    agentPerformance: agentPerf,
    agentCapabilities: agentCaps,
    loading: false,
    loadingCapabilities: false,
  },
};

export const WithFailedStep: Story = {
  args: {
    activeWorkflows: [
      {
        ...runningWorkflow,
        workflow_id: 'wf-live-fail',
        name: 'Failing Pipeline',
        steps: makeSteps(['completed', 'failed', 'pending', 'pending', 'pending', 'pending']),
      },
    ],
    agentPerformance: agentPerf,
    agentCapabilities: agentCaps,
    loading: false,
    loadingCapabilities: false,
  },
};
