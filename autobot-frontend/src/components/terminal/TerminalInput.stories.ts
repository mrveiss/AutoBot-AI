// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import TerminalInput from './TerminalInput.vue';

const meta = {
  title: 'Components/Terminal/TerminalInput',
  component: TerminalInput,
  tags: ['autodocs'],
  argTypes: {
    currentInput: {
      control: 'text',
      description: 'Current value of the command input field (v-model)',
    },
    currentPrompt: {
      control: 'text',
      description: 'Shell prompt string displayed before the input',
    },
    canInput: {
      control: 'boolean',
      description: 'Whether the user can type commands (connected state)',
    },
    showCursor: {
      control: 'boolean',
      description: 'Whether to display the blinking cursor indicator',
    },
    hasAutomatedWorkflow: {
      control: 'boolean',
      description: 'Whether an automated workflow is active (hides the Test Workflow button)',
    },
    commandHistory: {
      control: 'object',
      description: 'Array of previously executed commands for history navigation',
    },
  },
} as Meta<typeof TerminalInput>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

export const ReadyForInput: Story = {
  args: {
    currentInput: '',
    currentPrompt: 'user@autobot:~$ ',
    canInput: true,
    showCursor: true,
    hasAutomatedWorkflow: false,
    commandHistory: ['ls -la', 'git status', 'npm run dev'],
  },
};

export const WithPartialCommand: Story = {
  args: {
    currentInput: 'git commit -m "',
    currentPrompt: 'user@autobot:~/project$ ',
    canInput: true,
    showCursor: true,
    hasAutomatedWorkflow: false,
    commandHistory: ['git add .', 'git status'],
  },
};

export const Disabled: Story = {
  args: {
    currentInput: '',
    currentPrompt: '$ ',
    canInput: false,
    showCursor: false,
    hasAutomatedWorkflow: false,
    commandHistory: [],
  },
};

export const WithAutomatedWorkflow: Story = {
  args: {
    currentInput: '',
    currentPrompt: 'autobot@host:~$ ',
    canInput: true,
    showCursor: true,
    hasAutomatedWorkflow: true,
    commandHistory: ['sudo apt-get update'],
  },
};

export const EmptyHistory: Story = {
  args: {
    currentInput: '',
    currentPrompt: 'root@server:~# ',
    canInput: true,
    showCursor: true,
    hasAutomatedWorkflow: false,
    commandHistory: [],
  },
};
