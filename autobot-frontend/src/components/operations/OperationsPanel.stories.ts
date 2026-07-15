// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import OperationsPanel from './OperationsPanel.vue';

const meta = {
  title: 'Components/Operations/OperationsPanel',
  component: OperationsPanel,
  tags: ['autodocs'],
  argTypes: {
    operations: {
      control: 'object',
      description: 'Array of Operation objects shown in the list pane',
    },
    totalCount: {
      control: 'number',
      description: 'Total operation count (for footer display)',
    },
    loading: {
      control: 'boolean',
      description: 'Pass loading state through to OperationsList',
    },
    emptyMessage: {
      control: 'text',
      description: 'Custom text shown in the empty-state of the list pane',
    },
    filter: {
      control: 'object',
      description: 'Current OperationsFilter state',
    },
  },
} as Meta<typeof OperationsPanel>;

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
    description: 'Full sync of primary knowledge base.',
    created_at: '2026-05-16T08:00:00Z',
    started_at: '2026-05-16T08:01:00Z',
    completed_at: null,
    error_message: null,
    checkpoints_count: 2,
    can_resume: false,
    context: { source: 's3://autobot-docs' },
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
    description: 'Automated research task.',
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
    description: 'NPU fine-tuning run with custom dataset.',
    created_at: '2026-05-16T06:00:00Z',
    started_at: '2026-05-16T06:05:00Z',
    completed_at: '2026-05-16T06:45:00Z',
    error_message: 'CUDA out of memory',
    checkpoints_count: 1,
    can_resume: true,
    context: { dataset: 'custom-v3', epochs: 10 },
  },
];

const defaultFilter = { status: undefined, operation_type: undefined, limit: 50 };

export const Default: Story = {
  args: {
    operations: sampleOperations,
    totalCount: sampleOperations.length,
    loading: false,
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
    emptyMessage: 'No operations found. Start a new workflow to see activity here.',
    filter: defaultFilter,
  },
};

export const SingleRunningOperation: Story = {
  args: {
    operations: [sampleOperations[0]],
    totalCount: 1,
    loading: false,
    filter: defaultFilter,
  },
};

export const ManyOperations: Story = {
  args: {
    operations: [
      ...sampleOperations,
      {
        operation_id: 'op-004',
        name: 'Connector Scheduled Sync',
        operation_type: 'connector_sync',
        status: 'pending',
        priority: 'low',
        progress: 0,
        processed_items: 0,
        estimated_items: 500,
        current_step: '',
        description: 'Scheduled connector pull from external API.',
        created_at: '2026-05-16T09:00:00Z',
        started_at: null,
        completed_at: null,
        error_message: null,
        checkpoints_count: 0,
        can_resume: false,
        context: {},
      },
      {
        operation_id: 'op-005',
        name: 'Embedding Re-index',
        operation_type: 'knowledge_base_sync',
        status: 'paused',
        priority: 'normal',
        progress: 74,
        processed_items: 740,
        estimated_items: 1000,
        current_step: 'Paused at batch 15/20',
        description: '',
        created_at: '2026-05-16T05:00:00Z',
        started_at: '2026-05-16T05:05:00Z',
        completed_at: null,
        error_message: null,
        checkpoints_count: 5,
        can_resume: true,
        context: {},
      },
    ],
    totalCount: 5,
    loading: false,
    filter: defaultFilter,
  },
};
