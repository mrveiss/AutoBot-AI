// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import HostSelector from './HostSelector.vue';

const meta = {
  title: 'Components/UI/HostSelector',
  component: HostSelector,
  argTypes: {
    chatId: {
      control: 'text',
      description: 'Chat session ID used to scope host preferences',
    },
    requiredCapability: {
      control: 'select',
      options: [undefined, 'ssh', 'vnc'],
      description: 'Filter hosts to only those with this capability',
    },
    modelValue: {
      control: 'object',
      description: 'v-model: currently selected host (or null)',
    },
  },
} as Meta<typeof HostSelector>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

export const Default: Story = {
  args: {
    modelValue: null,
  },
};

export const SshOnly: Story = {
  args: {
    modelValue: null,
    requiredCapability: 'ssh',
  },
};

export const VncOnly: Story = {
  args: {
    modelValue: null,
    requiredCapability: 'vnc',
  },
};

export const WithChatContext: Story = {
  args: {
    modelValue: null,
    chatId: 'chat-123',
  },
};

export const Preselected: Story = {
  args: {
    modelValue: {
      id: 'host-1',
      name: 'Backend VM',
      host: '192.0.2.20',
      ssh_port: 22,
      capabilities: ['ssh'],
      os: 'Ubuntu 24.04',
    },
  },
};
