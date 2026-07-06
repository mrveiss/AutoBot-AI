// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import AuditStatistics from './AuditStatistics.vue';

const fullStatistics = {
  total_entries: 12340,
  success_count: 11200,
  denied_count: 820,
  failed_count: 240,
  error_count: 80,
  success_rate: 90.8,
  top_operations: [
    { operation: 'user_login', count: 4200 },
    { operation: 'file_read', count: 3100 },
    { operation: 'vm_start', count: 2200 },
    { operation: 'token_refresh', count: 1800 },
    { operation: 'connection_open', count: 1040 },
  ],
  top_users: [
    { user_id: 'alice', count: 5400 },
    { user_id: 'bob', count: 3200 },
    { user_id: 'carol', count: 2100 },
    { user_id: 'dave', count: 1100 },
    { user_id: 'eve', count: 540 },
  ],
};

const meta = {
  title: 'Components/Audit/AuditStatistics',
  component: AuditStatistics,
  tags: ['autodocs'],
  argTypes: {
    statistics: {
      control: 'object',
      description: 'AuditStatistics data object, or null when unavailable',
    },
    vmInfo: {
      control: 'object',
      description: 'Optional VM name/source info to display in the VM card',
    },
    loading: {
      control: 'boolean',
      description: 'Shows a loading overlay when true',
    },
    'onUser-click': { action: 'user-click' },
  },
} as Meta<typeof AuditStatistics>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

export const Default: Story = {
  args: {
    statistics: fullStatistics,
    vmInfo: null,
    loading: false,
  },
};

export const WithVmInfo: Story = {
  args: {
    statistics: fullStatistics,
    vmInfo: { vm_name: 'vm-worker-01', vm_source: 'proxmox' },
    loading: false,
  },
};

export const Loading: Story = {
  args: {
    statistics: null,
    vmInfo: null,
    loading: true,
  },
};

export const NoData: Story = {
  args: {
    statistics: null,
    vmInfo: null,
    loading: false,
  },
};

export const LowSuccessRate: Story = {
  args: {
    statistics: {
      ...fullStatistics,
      success_count: 600,
      denied_count: 5200,
      failed_count: 4200,
      error_count: 2340,
      success_rate: 48.7,
    },
    vmInfo: { vm_name: 'vm-prod-03', vm_source: 'proxmox' },
    loading: false,
  },
};

export const HighThroughput: Story = {
  args: {
    statistics: {
      ...fullStatistics,
      total_entries: 2500000,
      success_count: 2450000,
      denied_count: 35000,
      failed_count: 10000,
      error_count: 5000,
      success_rate: 98.0,
    },
    vmInfo: null,
    loading: false,
  },
};
