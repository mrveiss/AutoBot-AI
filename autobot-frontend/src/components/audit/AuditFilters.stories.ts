// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import AuditFilters from './AuditFilters.vue';

const defaultFilter = {
  dateRange: 'today' as const,
  startDate: null,
  endDate: null,
  operation: null,
  result: null,
  userId: null,
  sessionId: null,
  vmName: null,
  limit: 100,
};

const sampleOperationCategories = {
  Authentication: ['user_login', 'user_logout', 'token_refresh'],
  'VM Operations': ['vm_start', 'vm_stop', 'vm_snapshot', 'vm_delete'],
  'File System': ['file_read', 'file_write', 'file_delete'],
  Network: ['connection_open', 'connection_close', 'firewall_rule_add'],
};

const meta = {
  title: 'Components/Audit/AuditFilters',
  component: AuditFilters,
  tags: ['autodocs'],
  argTypes: {
    filter: {
      control: 'object',
      description: 'Current filter state (AuditFilter)',
    },
    operationCategories: {
      control: 'object',
      description: 'Grouped operation names for the operation dropdown',
    },
    'onUpdate:filter': { action: 'update:filter' },
    onApply: { action: 'apply' },
    onReset: { action: 'reset' },
  },
} as Meta<typeof AuditFilters>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

export const Default: Story = {
  args: {
    filter: { ...defaultFilter },
    operationCategories: sampleOperationCategories,
  },
};

export const WithActiveFilters: Story = {
  args: {
    filter: {
      ...defaultFilter,
      operation: 'user_login',
      result: 'denied',
      userId: 'alice',
    },
    operationCategories: sampleOperationCategories,
  },
};

export const CustomDateRange: Story = {
  args: {
    filter: {
      ...defaultFilter,
      dateRange: 'custom',
      startDate: '2026-05-01T00:00',
      endDate: '2026-05-15T23:59',
    },
    operationCategories: sampleOperationCategories,
  },
};

export const WeekRange: Story = {
  args: {
    filter: {
      ...defaultFilter,
      dateRange: 'week',
    },
    operationCategories: sampleOperationCategories,
  },
};

export const HighLimitWithSessionFilter: Story = {
  args: {
    filter: {
      ...defaultFilter,
      limit: 500,
      sessionId: 'abc12345',
      vmName: 'vm-worker-01',
    },
    operationCategories: sampleOperationCategories,
  },
};
