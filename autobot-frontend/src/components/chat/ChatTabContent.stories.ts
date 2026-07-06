// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import ChatTabContent from './ChatTabContent.vue';

const meta = {
  title: 'Components/Chat/ChatTabContent',
  component: ChatTabContent,
  tags: ['autodocs'],
  argTypes: {
    activeTab: {
      control: 'select',
      options: ['chat', 'files', 'terminal', 'browser', 'novnc'],
      description: 'Currently active tab key',
    },
    currentSessionId: {
      control: 'text',
      description: 'Current chat session ID',
    },
    novncUrl: {
      control: 'text',
      description: 'Legacy noVNC URL (kept for backwards compatibility)',
    },
  },
} as Meta<typeof ChatTabContent>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<Record<string, unknown>>;

export const ChatTab: Story = {
  args: {
    activeTab: 'chat',
    currentSessionId: 'session-001',
    novncUrl: '',
  },
  render: (args: Record<string, unknown>) => ({
    components: { ChatTabContent },
    setup() { return { args }; },
    template: `<div style="height:600px; overflow:hidden;"><ChatTabContent v-bind="args" /></div>`,
  }),
};

export const FilesTab: Story = {
  args: {
    activeTab: 'files',
    currentSessionId: 'session-001',
    novncUrl: '',
  },
  render: (args: Record<string, unknown>) => ({
    components: { ChatTabContent },
    setup() { return { args }; },
    template: `<div style="height:600px; overflow:hidden;"><ChatTabContent v-bind="args" /></div>`,
  }),
};

export const TerminalTab: Story = {
  args: {
    activeTab: 'terminal',
    currentSessionId: 'session-001',
    novncUrl: '',
  },
  render: (args: Record<string, unknown>) => ({
    components: { ChatTabContent },
    setup() { return { args }; },
    template: `<div style="height:600px; overflow:hidden;"><ChatTabContent v-bind="args" /></div>`,
  }),
};
