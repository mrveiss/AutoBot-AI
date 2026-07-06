// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import WorkflowHistory from './WorkflowHistory.vue';

const meta = {
  title: 'Components/Workflow/WorkflowHistory',
  component: WorkflowHistory,
  tags: ['autodocs'],
  argTypes: {
    workflows: {
      control: 'object',
      description: 'Active (finished) workflows to display in history',
    },
    completedWorkflows: {
      control: 'object',
      description: 'Persisted completed workflows (merged with workflows, deduplicated)',
    },
  },
} as Meta<typeof WorkflowHistory>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

const makeSteps = (statuses: string[]) =>
  statuses.map((status, i) => ({
    step_id: `step_${i}`,
    status,
    description: `Step ${i + 1}`,
    command: `cmd_${i}`,
    risk_level: 'low',
    requires_confirmation: false,
  }));

const sampleWorkflows = [
  {
    workflow_id: 'wf-001',
    name: 'Deploy Backend v2.4',
    description: 'Full deployment pipeline for backend service version 2.4',
    automation_mode: 'full_auto',
    total_steps: 5,
    current_step: 4,
    steps: makeSteps(['completed', 'completed', 'completed', 'completed', 'completed']),
    created_at: new Date(Date.now() - 3_600_000).toISOString(),
    started_at: new Date(Date.now() - 3_500_000).toISOString(),
    completed_at: new Date(Date.now() - 3_000_000).toISOString(),
    is_paused: false,
    is_cancelled: false,
    phase: 'complete',
  },
  {
    workflow_id: 'wf-002',
    name: 'Security Audit',
    description: 'Run automated security scanning on all services',
    automation_mode: 'supervised',
    total_steps: 4,
    current_step: 2,
    steps: makeSteps(['completed', 'completed', 'failed', 'pending']),
    created_at: new Date(Date.now() - 7_200_000).toISOString(),
    started_at: new Date(Date.now() - 7_100_000).toISOString(),
    completed_at: new Date(Date.now() - 6_000_000).toISOString(),
    is_paused: false,
    is_cancelled: false,
    phase: 'complete',
  },
  {
    workflow_id: 'wf-003',
    name: 'Database Migration',
    description: 'Migrate schema to v3 with data backfill',
    automation_mode: 'manual',
    total_steps: 6,
    current_step: 3,
    steps: makeSteps(['completed', 'completed', 'completed', 'pending', 'pending', 'pending']),
    created_at: new Date(Date.now() - 86_400_000).toISOString(),
    started_at: new Date(Date.now() - 86_300_000).toISOString(),
    completed_at: null,
    is_paused: false,
    is_cancelled: true,
    phase: 'executing',
  },
];

export const WithHistory: Story = {
  args: {
    workflows: sampleWorkflows,
    completedWorkflows: [],
  },
};

export const Empty: Story = {
  args: {
    workflows: [],
    completedWorkflows: [],
  },
};

export const MixedSources: Story = {
  args: {
    workflows: [sampleWorkflows[0]],
    completedWorkflows: [sampleWorkflows[1], sampleWorkflows[2]],
  },
};

export const SingleEntry: Story = {
  args: {
    workflows: [sampleWorkflows[0]],
    completedWorkflows: [],
  },
};

export const LargeHistory: Story = {
  args: {
    workflows: Array.from({ length: 15 }, (_, i) => ({
      workflow_id: `wf-bulk-${i}`,
      name: `Workflow ${i + 1}`,
      description: `Automated task batch ${i + 1}`,
      automation_mode: 'full_auto',
      total_steps: 3,
      current_step: 2,
      steps: makeSteps(['completed', 'completed', 'completed']),
      created_at: new Date(Date.now() - i * 3_600_000).toISOString(),
      started_at: new Date(Date.now() - i * 3_600_000 + 60_000).toISOString(),
      completed_at: new Date(Date.now() - i * 3_600_000 + 600_000).toISOString(),
      is_paused: false,
      is_cancelled: false,
      phase: 'complete',
    })),
    completedWorkflows: [],
  },
};
