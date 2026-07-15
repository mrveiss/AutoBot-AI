// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import OrchestrationVisualizer from './OrchestrationVisualizer.vue';

const meta = {
  title: 'Components/Workflow/OrchestrationVisualizer',
  component: OrchestrationVisualizer,
  tags: ['autodocs'],
  argTypes: {
    status: {
      control: 'object',
      description: 'Orchestration system status object',
    },
    strategies: {
      control: 'object',
      description: 'Available execution strategies keyed by strategy name',
    },
    currentWorkflow: {
      control: 'object',
      description: 'Currently active workflow, or null if none',
    },
    loading: {
      control: 'boolean',
      description: 'Whether strategies are loading',
    },
  },
} as Meta<typeof OrchestrationVisualizer>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

const sampleStatus = {
  status: 'operational',
  active_workflows: 3,
  total_agents: 8,
  max_parallel_tasks: 5,
  capabilities: {
    agent_coordination: true,
    performance_tracking: true,
    automatic_failover: true,
    resource_optimization: false,
  },
};

const sampleStrategies = {
  sequential: {
    name: 'Sequential',
    description: 'Execute tasks one at a time in order.',
    best_for: 'Dependent tasks with strict ordering',
  },
  parallel: {
    name: 'Parallel',
    description: 'Execute independent tasks simultaneously.',
    best_for: 'Independent tasks with no dependencies',
  },
  pipeline: {
    name: 'Pipeline',
    description: 'Stream results from one stage to the next.',
    best_for: 'Data processing workflows',
  },
  collaborative: {
    name: 'Collaborative',
    description: 'Multiple agents cooperate on a single task.',
    best_for: 'Complex tasks requiring diverse expertise',
  },
};

const sampleWorkflow = {
  workflow_id: 'wf-001',
  name: 'Deploy Backend Service',
  description: 'Full CI/CD deployment pipeline',
  automation_mode: 'full_auto',
  current_step: 2,
  total_steps: 5,
  is_paused: false,
  is_cancelled: false,
  completed_at: null,
  phase: 'executing',
  steps: [
    { step_id: 's1', status: 'completed', description: 'Run unit tests', command: 'pytest', risk_level: 'low', requires_confirmation: false },
    { step_id: 's2', status: 'completed', description: 'Build Docker image', command: 'docker build', risk_level: 'low', requires_confirmation: false },
    { step_id: 's3', status: 'executing', description: 'Push to registry', command: 'docker push', risk_level: 'medium', requires_confirmation: false },
    { step_id: 's4', status: 'pending', description: 'Deploy to staging', command: 'kubectl apply', risk_level: 'high', requires_confirmation: true },
    { step_id: 's5', status: 'pending', description: 'Run smoke tests', command: 'pytest smoke/', risk_level: 'low', requires_confirmation: false },
  ],
};

export const Operational: Story = {
  args: {
    status: sampleStatus,
    strategies: sampleStrategies,
    currentWorkflow: sampleWorkflow,
    loading: false,
  },
};

export const NoActiveWorkflow: Story = {
  args: {
    status: sampleStatus,
    strategies: sampleStrategies,
    currentWorkflow: null,
    loading: false,
  },
};

export const LoadingStrategies: Story = {
  args: {
    status: sampleStatus,
    strategies: {},
    currentWorkflow: null,
    loading: true,
  },
};

export const DegradedStatus: Story = {
  args: {
    status: {
      status: 'degraded',
      active_workflows: 1,
      total_agents: 3,
      max_parallel_tasks: 2,
      capabilities: {
        agent_coordination: true,
        performance_tracking: false,
        automatic_failover: false,
        resource_optimization: false,
      },
    },
    strategies: sampleStrategies,
    currentWorkflow: null,
    loading: false,
  },
};

export const CompletedWorkflow: Story = {
  args: {
    status: sampleStatus,
    strategies: sampleStrategies,
    currentWorkflow: {
      ...sampleWorkflow,
      current_step: 4,
      completed_at: new Date().toISOString(),
      steps: sampleWorkflow.steps.map(s => ({ ...s, status: 'completed' })),
    },
    loading: false,
  },
};
