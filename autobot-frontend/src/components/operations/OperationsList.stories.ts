// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import OperationsList from './OperationsList.vue';

const meta = {
  title: 'Components/Operations/OperationsList',
  component: OperationsList,
  tags: ['autodocs'],
  argTypes: {
    operations: {
      control: 'object',
      description: 'Array of Operation objects to display in the table',
    },
    totalCount: {
      control: 'number',
      description: 'Total operation count (may exceed the displayed slice)',
    },
    loading: {
      control: 'boolean',
      description: 'Show loading spinner instead of table',
    },
    selectedId: {
      control: 'text',
      description: 'operation_id of the currently selected row (highlighted)',
    },
    emptyMessage: {
      control: 'text',
      description: 'Custom empty-state body text',
    },
    filter: {
      control: 'object',
      description: 'Current OperationsFilter state',
    },
  },
} as Meta<typeof OperationsList>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = import('@storybook/vue3').StoryObj<Record<string, unknown>>;

const sampleOperations = [
  {
    operation_id: 'op-001',
    name: 'Knowledge Base Sync',
    operation_type: 'knowledge_base_sync',
    status: 'running',
    priority: 'normal',
    progress: 52,
    processed_items: 520,
    estimated_items: 1000,
    current_step: 'Embedding batch 6/20',
    description: '',
    created_at: '2026-05-16T08:00:00Z',
    started_at: '2026-05-16T08:01:00Z',
    completed_at: null,
    error_message: null,
    checkpoints_count: 2,
    can_resume: false,
    context: {},
  },
  {
    operation_id: 'op-002',
    name: 'Agent Task Execution',
    operation_type: 'agent_task',
    status: 'completed',
    priority: 'normal',
    progress: 100,
    processed_items: 200,
    estimated_items: 200,
    current_step: '',
    description: '',
    created_at: '2026-05-16T07:00:00Z',
    started_at: '2026-05-16T07:00:30Z',
    completed_at: '2026-05-16T07:45:00Z',
    error_message: null,
    checkpoints_count: 0,
    can_resume: false,
    context: {},
  },
  {
    operation_id: 'op-003',
    name: 'Model Fine-Tune',
    operation_type: 'model_training',
    status: 'failed',
    priority: 'high',
    progress: 31,
    processed_items: 310,
    estimated_items: 1000,
    current_step: 'Epoch 3 / 10',
    description: '',
    created_at: '2026-05-16T06:00:00Z',
    started_at: '2026-05-16T06:05:00Z',
    completed_at: '2026-05-16T06:45:00Z',
    error_message: 'CUDA out of memory',
    checkpoints_count: 1,
    can_resume: true,
    context: {},
  },
];

const defaultFilter = { status: undefined, operation_type: undefined, limit: 50 };

export const WithOperations: Story = {
  args: {
    operations: sampleOperations,
    totalCount: sampleOperations.length,
    loading: false,
    selectedId: null,
    filter: defaultFilter,
  },
};

export const WithSelectedRow: Story = {
  args: {
    operations: sampleOperations,
    totalCount: sampleOperations.length,
    loading: false,
    selectedId: 'op-001',
    filter: defaultFilter,
  },
};

export const Loading: Story = {
  args: {
    operations: [],
    totalCount: 0,
    loading: true,
    filter: defaultFilter,
  },
};

export const Empty: Story = {
  args: {
    operations: [],
    totalCount: 0,
    loading: false,
    emptyMessage: 'No operations match your current filters.',
    filter: defaultFilter,
  },
};

export const SingleOperation: Story = {
  args: {
    operations: [sampleOperations[0]],
    totalCount: 1,
    loading: false,
    filter: defaultFilter,
  },
};
