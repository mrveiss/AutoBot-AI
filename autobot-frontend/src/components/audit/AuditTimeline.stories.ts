import type { Meta, StoryObj } from '@storybook/vue3';
import AuditTimeline from './AuditTimeline.vue';

const makeEntry = (
  id: string,
  operation: string,
  result: 'success' | 'denied' | 'failed' | 'error',
  overrides: Record<string, unknown> = {}
) => ({
  id,
  timestamp: new Date(Date.now() - parseInt(id) * 300000).toISOString(),
  operation,
  result,
  user_id: 'alice',
  session_id: 'sess-abc12345',
  vm_name: 'vm-worker-01',
  vm_source: 'proxmox',
  ip_address: '192.168.1.10',
  error_message: null,
  details: {},
  ...overrides,
});

const sessionEntries = [
  makeEntry('1', 'user_login', 'success'),
  makeEntry('2', 'file_read', 'success', { details: { path: '/home/alice/config.yaml' } }),
  makeEntry('3', 'vm_start', 'success', { user_id: 'bob' }),
  makeEntry('4', 'vm_snapshot', 'denied', { error_message: 'Permission denied: snapshot on protected VM' }),
  makeEntry('5', 'user_logout', 'success'),
];

const userEntries = [
  makeEntry('1', 'user_login', 'success', { session_id: 'sess-aaa11111' }),
  makeEntry('2', 'token_refresh', 'success', { session_id: 'sess-aaa11111' }),
  makeEntry('3', 'file_write', 'failed', {
    session_id: 'sess-bbb22222',
    error_message: 'Disk quota exceeded',
  }),
  makeEntry('4', 'connection_open', 'error', {
    session_id: 'sess-ccc33333',
    error_message: 'Network unreachable',
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
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

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
      makeEntry('2', 'vm_delete', 'denied', { error_message: 'Unauthorized: VM is protected' }),
      makeEntry('3', 'firewall_rule_add', 'error', {
        error_message: 'Internal error: firewall daemon unreachable',
        details: { rule: 'DENY tcp 0.0.0.0/0 22', attempt: 3 },
      }),
      makeEntry('4', 'user_logout', 'failed', { error_message: 'Session already expired' }),
    ],
    loading: false,
  },
};
