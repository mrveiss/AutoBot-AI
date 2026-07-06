// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import OperationFilters from './OperationFilters.vue';

const meta = {
  title: 'Components/Operations/OperationFilters',
  component: OperationFilters,
  tags: ['autodocs'],
  argTypes: {
    filter: {
      control: 'object',
      description: 'Current filter state: { status?, operation_type?, limit }',
    },
  },
} as Meta<typeof OperationFilters>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = import('@storybook/vue3').StoryObj<Record<string, unknown>>;

export const Default: Story = {
  args: {
    filter: {
      status: undefined,
      operation_type: undefined,
      limit: 50,
    },
  },
};

export const StatusFiltered: Story = {
  args: {
    filter: {
      status: 'running',
      operation_type: undefined,
      limit: 50,
    },
  },
};

export const TypeFiltered: Story = {
  args: {
    filter: {
      status: undefined,
      operation_type: 'knowledge_base_sync',
      limit: 50,
    },
  },
};

export const FullyFiltered: Story = {
  args: {
    filter: {
      status: 'completed',
      operation_type: 'agent_task',
      limit: 25,
    },
  },
};

export const HighLimit: Story = {
  args: {
    filter: {
      status: undefined,
      operation_type: undefined,
      limit: 250,
    },
  },
};
