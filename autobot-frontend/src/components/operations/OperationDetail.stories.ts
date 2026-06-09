// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import OperationDetail from './OperationDetail.vue';

const meta = {
  title: 'Components/Operations/OperationDetail',
  component: OperationDetail,
  tags: ['autodocs'],
  argTypes: {
    operation: {
      control: 'object',
      description: 'Full Operation object to display',
    },
  },
} as Meta<typeof OperationDetail>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = import('@storybook/vue3').StoryObj<any>;

const baseOperation = {
  operation_id: 'op-abc123',
  name: 'Knowledge Base Sync',
  operation_type: 'knowledge_base_sync',
  status: 'running',
  priority: 'normal',
  progress: 52,
  processed_items: 520,
  estimated_items: 1000,
  current_step: 'Embedding document batch 6 of 20',
  description: 'Full synchronisation of the primary knowledge base with updated document corpus.',
  created_at: '2026-05-16T08:00:00Z',
  started_at: '2026-05-16T08:01:00Z',
  completed_at: null,
  error_message: null,
  checkpoints_count: 3,
  can_resume: false,
  context: { source: 's3://autobot-docs', batch_size: 50 },
};

export const Running: Story = {
  args: {
    operation: baseOperation,
  },
};

export const Completed: Story = {
  args: {
    operation: {
      ...baseOperation,
      operation_id: 'op-done456',
      name: 'Agent Task Execution',
      operation_type: 'agent_task',
      status: 'completed',
      progress: 100,
      processed_items: 1000,
      current_step: '',
      completed_at: '2026-05-16T08:45:00Z',
      checkpoints_count: 0,
    },
  },
};

export const Failed: Story = {
  args: {
    operation: {
      ...baseOperation,
      operation_id: 'op-fail789',
      name: 'Model Fine-Tune',
      operation_type: 'model_training',
      status: 'failed',
      progress: 31,
      processed_items: 310,
      current_step: 'Epoch 3 / 10',
      completed_at: '2026-05-16T09:10:00Z',
      error_message: 'CUDA out of memory: tried to allocate 2.00 GiB\n  at batch 31 of epoch 3',
      checkpoints_count: 1,
      can_resume: true,
    },
  },
};

export const HighPriority: Story = {
  args: {
    operation: {
      ...baseOperation,
      operation_id: 'op-crit001',
      name: 'Critical Data Migration',
      priority: 'critical',
      status: 'running',
      description: 'Emergency migration of production data following schema update.',
      context: {},
    },
  },
};

export const NoContext: Story = {
  args: {
    operation: {
      ...baseOperation,
      operation_id: 'op-nocontext',
      context: {},
      description: '',
      checkpoints_count: 0,
    },
  },
};
