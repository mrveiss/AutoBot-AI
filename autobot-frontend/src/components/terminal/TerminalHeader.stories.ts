// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import TerminalHeader from './TerminalHeader.vue';

const meta = {
  title: 'Components/Terminal/TerminalHeader',
  component: TerminalHeader,
  tags: ['autodocs'],
  argTypes: {
    sessionTitle: {
      control: 'text',
      description: 'Title displayed in the window header',
    },
    hasRunningProcesses: {
      control: 'boolean',
      description: 'Whether there are active processes (enables Emergency Kill button)',
    },
    automationPaused: {
      control: 'boolean',
      description: 'Whether automation is currently paused (shows RESUME vs PAUSE)',
    },
    hasAutomatedWorkflow: {
      control: 'boolean',
      description: 'Whether an automated workflow is active (enables PAUSE/RESUME button)',
    },
    hasActiveProcess: {
      control: 'boolean',
      description: 'Whether a process is currently active (enables Interrupt button)',
    },
    connecting: {
      control: 'boolean',
      description: 'Whether the terminal is in the process of connecting (disables Reconnect button)',
    },
  },
} as Meta<typeof TerminalHeader>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Idle: Story = {
  args: {
    sessionTitle: 'Main Terminal',
    hasRunningProcesses: false,
    automationPaused: false,
    hasAutomatedWorkflow: false,
    hasActiveProcess: false,
    connecting: false,
  },
};

export const ActiveProcess: Story = {
  args: {
    sessionTitle: 'Running: npm install',
    hasRunningProcesses: true,
    automationPaused: false,
    hasAutomatedWorkflow: false,
    hasActiveProcess: true,
    connecting: false,
  },
};

export const AutomationRunning: Story = {
  args: {
    sessionTitle: 'Automated Workflow: Deploy',
    hasRunningProcesses: true,
    automationPaused: false,
    hasAutomatedWorkflow: true,
    hasActiveProcess: true,
    connecting: false,
  },
};

export const AutomationPaused: Story = {
  args: {
    sessionTitle: 'Paused Workflow: Deploy',
    hasRunningProcesses: false,
    automationPaused: true,
    hasAutomatedWorkflow: true,
    hasActiveProcess: false,
    connecting: false,
  },
};

export const Reconnecting: Story = {
  args: {
    sessionTitle: 'Terminal (Reconnecting...)',
    hasRunningProcesses: false,
    automationPaused: false,
    hasAutomatedWorkflow: false,
    hasActiveProcess: false,
    connecting: true,
  },
};
