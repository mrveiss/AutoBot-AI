// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import Terminal from './Terminal.vue';

const meta = {
  title: 'Components/Terminal/Terminal',
  component: Terminal,
  tags: ['autodocs'],
  argTypes: {
    sessionType: {
      control: 'select',
      options: ['simple', 'secure', 'main'],
      description: 'Type of terminal session to establish',
    },
    autoConnect: {
      control: 'boolean',
      description: 'Automatically connect to the backend terminal service on mount',
    },
    chatSessionId: {
      control: 'text',
      description: 'Optional chat session ID to link terminal to a conversation (null for standalone)',
    },
  },
} as Meta<typeof Terminal>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

// NOTE: Terminal uses WebSocket for real-time connection.  In Storybook it will
// render in a disconnected state since there is no backend available.  All
// interactive controls (connect/disconnect, clear, copy) remain fully visible.

export const SimpleSession: Story = {
  render: () => ({
    components: { Terminal },
    template: `
      <div style="width: 900px; height: 600px;">
        <Terminal session-type="simple" :auto-connect="false" />
      </div>
    `,
  }),
};

export const SecureSession: Story = {
  render: () => ({
    components: { Terminal },
    template: `
      <div style="width: 900px; height: 600px;">
        <Terminal session-type="secure" :auto-connect="false" />
      </div>
    `,
  }),
};

export const WithChatSession: Story = {
  render: () => ({
    components: { Terminal },
    template: `
      <div style="width: 900px; height: 600px;">
        <Terminal session-type="simple" :auto-connect="false" chat-session-id="chat-story-session-001" />
      </div>
    `,
  }),
};

export const MainSession: Story = {
  render: () => ({
    components: { Terminal },
    template: `
      <div style="width: 900px; height: 600px;">
        <Terminal session-type="main" :auto-connect="false" />
      </div>
    `,
  }),
};

export const CompactLayout: Story = {
  render: () => ({
    components: { Terminal },
    template: `
      <div style="width: 600px; height: 400px;">
        <Terminal session-type="simple" :auto-connect="false" />
      </div>
    `,
  }),
};
