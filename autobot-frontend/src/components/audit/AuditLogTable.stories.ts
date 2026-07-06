// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import AuditLogTable from './AuditLogTable.vue';

const makeEntry = (
  id: string,
  operation: string,
  result: 'success' | 'denied' | 'failed' | 'error',
  overrides: Record<string, unknown> = {}
) => ({
  id,
  timestamp: new Date(Date.now() - Math.random() * 3600000).toISOString(),
  operation,
  result,
  user_id: 'alice',
  session_id: `sess-${id}`,
  vm_name: 'vm-worker-01',
  vm_source: 'proxmox',
  ip_address: '192.168.1.10',
  error_message: null,
  details: {},
  ...overrides,
});

const sampleEntries = [
  makeEntry('1', 'user_login', 'success'),
  makeEntry('2', 'file_read', 'success', { user_id: 'bob', vm_name: 'vm-dev-02' }),
  makeEntry('3', 'vm_snapshot', 'denied', { error_message: 'Permission denied for snapshot on protected VM' }),
  makeEntry('4', 'token_refresh', 'failed', { error_message: 'Token expired' }),
  makeEntry('5', 'connection_open', 'error', { error_message: 'Network unreachable' }),
  makeEntry('6', 'user_logout', 'success', { session_id: null, user_id: null }),
];

const meta = {
  title: 'Components/Audit/AuditLogTable',
  component: AuditLogTable,
  tags: ['autodocs'],
  argTypes: {
    entries: {
      control: 'object',
      description: 'Array of AuditEntry objects to display',
    },
    loading: {
      control: 'boolean',
      description: 'Shows a loading overlay when true',
    },
    hasMore: {
      control: 'boolean',
      description: 'Enables the Next Page button and shows "more available" indicator',
    },
    currentPage: {
      control: 'number',
      description: 'Current pagination page number',
    },
    onRefresh: { action: 'refresh' },
    onExport: { action: 'export' },
    'onEntry-select': { action: 'entry-select' },
    'onUser-click': { action: 'user-click' },
    'onSession-click': { action: 'session-click' },
    'onNext-page': { action: 'next-page' },
    'onPrev-page': { action: 'prev-page' },
  },
} as Meta<typeof AuditLogTable>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

export const Default: Story = {
  args: {
    entries: sampleEntries,
    loading: false,
    hasMore: false,
    currentPage: 1,
  },
};

export const Loading: Story = {
  args: {
    entries: [],
    loading: true,
    hasMore: false,
    currentPage: 1,
  },
};

export const Empty: Story = {
  args: {
    entries: [],
    loading: false,
    hasMore: false,
    currentPage: 1,
  },
};

export const WithPagination: Story = {
  args: {
    entries: sampleEntries,
    loading: false,
    hasMore: true,
    currentPage: 3,
  },
};

export const MixedResults: Story = {
  args: {
    entries: [
      makeEntry('a', 'vm_start', 'success'),
      makeEntry('b', 'vm_delete', 'denied', { error_message: 'Unauthorized VM deletion attempt' }),
      makeEntry('c', 'firewall_rule_add', 'failed', { user_id: null, session_id: null, vm_name: null }),
      makeEntry('d', 'file_write', 'error', {
        details: { file: '/etc/passwd', size_bytes: 4096 },
        error_message: 'Disk quota exceeded',
      }),
    ],
    loading: false,
    hasMore: false,
    currentPage: 1,
  },
};
