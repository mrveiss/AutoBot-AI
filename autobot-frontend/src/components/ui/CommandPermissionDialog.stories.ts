import type { Meta, StoryObj } from '@storybook/vue3';
import CommandPermissionDialog from './CommandPermissionDialog.vue';

const meta = {
  title: 'Components/UI/CommandPermissionDialog',
  component: CommandPermissionDialog,
  argTypes: {
    show: {
      control: 'boolean',
      description: 'Show the permission dialog',
    },
    command: {
      control: 'text',
      description: 'The shell command awaiting approval',
    },
    purpose: {
      control: 'text',
      description: 'Why the agent wants to run this command',
    },
    riskLevel: {
      control: 'select',
      options: ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'],
      description: 'Risk classification for the command',
    },
    chatId: {
      control: 'text',
      description: 'Chat session ID for feedback comments',
    },
    originalMessage: {
      control: 'text',
      description: 'Original user message that triggered the command',
    },
    terminalSessionId: {
      control: 'text',
      description: 'Terminal session ID for approval API call',
    },
  },
} as Meta<typeof CommandPermissionDialog>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    show: true,
    command: 'ls -la /home/user',
    purpose: 'Listing files in the user home directory',
    riskLevel: 'LOW',
    terminalSessionId: 'session-123',
  },
};

export const LowRisk: Story = {
  args: {
    show: true,
    command: 'cat /etc/hostname',
    purpose: 'Read the current machine hostname',
    riskLevel: 'LOW',
    terminalSessionId: 'session-low',
  },
};

export const MediumRisk: Story = {
  args: {
    show: true,
    command: 'systemctl restart nginx',
    purpose: 'Restart the nginx web server to pick up new configuration',
    riskLevel: 'MEDIUM',
    terminalSessionId: 'session-medium',
  },
};

export const HighRisk: Story = {
  args: {
    show: true,
    command: 'apt-get install -y postgresql-15',
    purpose: 'Install PostgreSQL 15 system-wide',
    riskLevel: 'HIGH',
    terminalSessionId: 'session-high',
  },
};

export const CriticalRisk: Story = {
  args: {
    show: true,
    command: 'rm -rf /var/lib/postgresql/data',
    purpose: 'Remove PostgreSQL data directory before reinstall',
    riskLevel: 'CRITICAL',
    terminalSessionId: 'session-critical',
  },
};

export const NoPurpose: Story = {
  args: {
    show: true,
    command: 'whoami',
    riskLevel: 'LOW',
    terminalSessionId: 'session-nopurpose',
  },
};
