// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import HostSelectionDialog from './HostSelectionDialog.vue';

const meta = {
  title: 'Components/UI/HostSelectionDialog',
  component: HostSelectionDialog,
  argTypes: {
    show: {
      control: 'boolean',
      description: 'Show the dialog',
    },
    command: {
      control: 'text',
      description: 'Optional command preview to show above host list',
    },
    purpose: {
      control: 'text',
      description: 'Why the agent needs to choose a host',
    },
    requestId: {
      control: 'text',
      description: 'Backend request ID for correlation',
    },
    agentSessionId: {
      control: 'text',
      description: 'Agent session that initiated the request',
    },
  },
} as Meta<typeof HostSelectionDialog>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

export const Default: Story = {
  args: {
    show: true,
    command: 'docker ps -a',
    purpose: 'List running containers on the selected host',
    requestId: 'req-001',
    agentSessionId: 'agent-001',
  },
};

export const NoCommand: Story = {
  args: {
    show: true,
    purpose: 'Open a remote shell on the chosen host',
    requestId: 'req-002',
    agentSessionId: 'agent-002',
  },
};

export const InfrastructureManagement: Story = {
  args: {
    show: true,
    command: 'systemctl status autobot-backend',
    purpose: 'Check backend service health',
    requestId: 'req-003',
  },
};

export const VncAccess: Story = {
  args: {
    show: true,
    command: 'xdotool key Return',
    purpose: 'Send a keystroke through VNC to the desktop host',
    requestId: 'req-004',
  },
};
