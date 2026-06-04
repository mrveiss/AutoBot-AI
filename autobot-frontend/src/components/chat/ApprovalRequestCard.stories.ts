import type { Meta } from '@storybook/vue3';
import ApprovalRequestCard from './ApprovalRequestCard.vue';

const meta = {
  title: 'Components/Chat/ApprovalRequestCard',
  component: ApprovalRequestCard,
  tags: ['autodocs'],
  argTypes: {
    status: {
      control: 'select',
      options: [null, 'pre_approved', 'approved', 'denied'],
      description: 'Approval status',
    },
    requiresApproval: {
      control: 'boolean',
      description: 'Whether the command requires approval',
    },
    command: {
      control: 'text',
      description: 'The command to be approved',
    },
    riskLevel: {
      control: 'select',
      options: ['low', 'medium', 'high', 'critical'],
      description: 'Risk level of the command',
    },
    purpose: {
      control: 'text',
      description: 'Purpose of the command',
    },
    processing: {
      control: 'boolean',
      description: 'Whether approval is being processed',
    },
  },
} as Meta<typeof ApprovalRequestCard>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<any>;

export const Pending: Story = {
  args: {
    status: null,
    requiresApproval: true,
    command: 'rm -rf /tmp/cache',
    riskLevel: 'medium',
    purpose: 'Clear temporary cache files to free disk space',
    reasons: ['Writes to filesystem', 'Irreversible operation'],
    sessionId: 'session-abc-123',
  },
};

export const Approved: Story = {
  args: {
    status: 'approved',
    command: 'systemctl restart nginx',
    comment: 'Approved — routine service restart after config update',
    riskLevel: 'low',
  },
};

export const Denied: Story = {
  args: {
    status: 'denied',
    command: 'DROP TABLE users;',
    comment: 'Denied — destructive database operation',
    riskLevel: 'critical',
  },
};

export const PreApproved: Story = {
  args: {
    status: 'pre_approved',
    command: 'ls -la /var/log',
    comment: 'Auto-approved: read-only filesystem command',
    riskLevel: 'low',
  },
};
