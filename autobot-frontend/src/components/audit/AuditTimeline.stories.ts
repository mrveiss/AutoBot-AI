// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import AuditTimeline from './AuditTimeline.vue';

const makeEntry = (
  id: string,
  operation: string,
  result: 'success' | 'denied' | 'failed' | 'error',
  overrides: Record<string, unknown> = {}
) => ({
  id,
  date: '2026-10-31',
  timestamp: (Date.now() - parseInt(id) * 300000) / 1000,
  operation,
  result,
  user_id: 'alice',
  session_id: 'sess-abc12345',
  vm_name: 'vm-worker-01',
  vm_source: 'proxmox',
  ip_address: '192.168.1.10',
  user_role: null,
  resource: null,
  performance_ms: null,
  details: {},
  ...overrides,
});

const sessionEntries = [
  makeEntry('1', 'user_login', 'success'),
  makeEntry('2', 'file_read', 'success', { details: { path: '/home/alice/config.yaml' } }),
  makeEntry('3', 'vm_start', 'success', { user_id: 'bob' }),
  makeEntry('4', 'vm_snapshot', 'denied', { details: { reason: 'Permission denied: snapshot on protected VM' } }),
  makeEntry('5', 'user_logout', 'success'),
];

const userEntries = [
  makeEntry('1', 'user_login', 'success', { session_id: 'sess-aaa11111' }),
  makeEntry('2', 'token_refresh', 'success', { session_id: 'sess-aaa11111' }),
  makeEntry('3', 'file_write', 'failed', {
    session_id: 'sess-bbb22222',
    details: { reason: 'Disk quota exceeded' },
  }),
  makeEntry('4', 'connection_open', 'error', {
    session_id: 'sess-ccc33333',
    details: { reason: 'Network unreachable' },
    ip_address: '10.0.0.5',
  }),
];

const meta = {
  title: 'Components/Audit/AuditTimeline',
  component: AuditTimeline,
  tags: ['autodocs'],
  argTypes: {
    type: {
      control: 'select',
      options: ['session', 'user'],
      description: 'Whether this timeline shows a session trail or user activity',
    },
    entityId: {
      control: 'text',
      description: 'The session ID or user ID being displayed',
    },
    entries: {
      control: 'object',
      description: 'Array of AuditEntry objects shown in the timeline',
    },
    loading: {
      control: 'boolean',
      description: 'Shows a loading spinner instead of entries when true',
    },
    onClose: { action: 'close' },
    onRefresh: { action: 'refresh' },
  },
} as Meta<typeof AuditTimeline>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

export const SessionTimeline: Story = {
  args: {
    type: 'session',
    entityId: 'sess-abc12345',
    entries: sessionEntries,
    loading: false,
  },
};

export const UserTimeline: Story = {
  args: {
    type: 'user',
    entityId: 'alice',
    entries: userEntries,
    loading: false,
  },
};

export const Loading: Story = {
  args: {
    type: 'session',
    entityId: 'sess-xyz99999',
    entries: [],
    loading: true,
  },
};

export const Empty: Story = {
  args: {
    type: 'user',
    entityId: 'nobody',
    entries: [],
    loading: false,
  },
};

export const WithErrors: Story = {
  args: {
    type: 'session',
    entityId: 'sess-err00001',
    entries: [
      makeEntry('1', 'user_login', 'success'),
      makeEntry('2', 'vm_delete', 'denied', { details: { reason: 'Unauthorized: VM is protected' } }),
      makeEntry('3', 'firewall_rule_add', 'error', {
        details: { reason: 'Internal error: firewall daemon unreachable', rule: 'DENY tcp 0.0.0.0/0 22', attempt: 3 },
      }),
      makeEntry('4', 'user_logout', 'failed', { details: { reason: 'Session already expired' } }),
    ],
    loading: false,
  },
};
