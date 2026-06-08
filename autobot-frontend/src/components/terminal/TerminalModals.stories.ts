// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import TerminalModals from './TerminalModals.vue';

const sampleProcesses = [
  { pid: 1234, command: 'npm run dev', startTime: new Date() },
  { pid: 5678, command: 'webpack --watch', startTime: new Date() },
];

const sampleWorkflowStep = {
  stepNumber: 2,
  totalSteps: 4,
  command: 'sudo systemctl restart nginx',
  description: 'Restart web server',
  explanation: 'Applies the new configuration by restarting the nginx service.',
};

const meta = {
  title: 'Components/Terminal/TerminalModals',
  component: TerminalModals,
  tags: ['autodocs'],
  argTypes: {
    showReconnectModal: {
      control: 'boolean',
      description: 'Show the connection-lost / reconnect modal',
    },
    showCommandConfirmation: {
      control: 'boolean',
      description: 'Show the destructive command confirmation modal',
    },
    showKillConfirmation: {
      control: 'boolean',
      description: 'Show the emergency kill all processes confirmation modal',
    },
    showLegacyModal: {
      control: 'boolean',
      description: 'Show the legacy workflow step confirmation modal',
    },
    pendingCommand: {
      control: 'text',
      description: 'The command pending confirmation in the command modal',
    },
    pendingCommandRisk: {
      control: 'select',
      options: ['low', 'medium', 'high', 'critical'],
      description: 'Risk level classification of the pending command',
    },
    pendingCommandReasons: {
      control: 'object',
      description: 'List of reasons explaining why the command is risky',
    },
    runningProcesses: {
      control: 'object',
      description: 'List of currently running processes (shown in kill confirmation)',
    },
    pendingWorkflowStep: {
      control: 'object',
      description: 'The workflow step awaiting confirmation in the legacy modal',
    },
  },
} as Meta<typeof TerminalModals>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const AllHidden: Story = {
  args: {
    showReconnectModal: false,
    showCommandConfirmation: false,
    showKillConfirmation: false,
    showLegacyModal: false,
    pendingCommand: '',
    pendingCommandRisk: 'low',
    pendingCommandReasons: [],
    runningProcesses: [],
    pendingWorkflowStep: null,
  },
};

export const ReconnectModal: Story = {
  args: {
    showReconnectModal: true,
    showCommandConfirmation: false,
    showKillConfirmation: false,
    showLegacyModal: false,
    pendingCommand: '',
    pendingCommandRisk: 'low',
    pendingCommandReasons: [],
    runningProcesses: [],
    pendingWorkflowStep: null,
  },
};

export const CommandConfirmationHighRisk: Story = {
  args: {
    showReconnectModal: false,
    showCommandConfirmation: true,
    showKillConfirmation: false,
    showLegacyModal: false,
    pendingCommand: 'rm -rf /var/data/*',
    pendingCommandRisk: 'high',
    pendingCommandReasons: [
      'Uses recursive deletion flag (-r)',
      'Targets a non-empty directory',
      'Cannot be undone without backup restoration',
    ],
    runningProcesses: [],
    pendingWorkflowStep: null,
  },
};

export const EmergencyKillModal: Story = {
  args: {
    showReconnectModal: false,
    showCommandConfirmation: false,
    showKillConfirmation: true,
    showLegacyModal: false,
    pendingCommand: '',
    pendingCommandRisk: 'low',
    pendingCommandReasons: [],
    runningProcesses: sampleProcesses,
    pendingWorkflowStep: null,
  },
};

export const LegacyWorkflowModal: Story = {
  args: {
    showReconnectModal: false,
    showCommandConfirmation: false,
    showKillConfirmation: false,
    showLegacyModal: true,
    pendingCommand: '',
    pendingCommandRisk: 'low',
    pendingCommandReasons: [],
    runningProcesses: [],
    pendingWorkflowStep: sampleWorkflowStep,
  },
};
