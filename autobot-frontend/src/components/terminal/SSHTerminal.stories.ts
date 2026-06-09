// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import SSHTerminal from './SSHTerminal.vue';

const meta = {
  title: 'Components/Terminal/SSHTerminal',
  component: SSHTerminal,
  tags: ['autodocs'],
  argTypes: {
    hostId: {
      control: 'text',
      description: 'The host ID to connect to via SSH WebSocket',
    },
    chatSessionId: {
      control: 'text',
      description: 'Optional chat session ID to link terminal to a conversation',
    },
  },
} as Meta<typeof SSHTerminal>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

// NOTE: SSHTerminal establishes a WebSocket connection on mount.  In Storybook
// the WebSocket will fail gracefully — the component renders in the
// "Disconnected" state with a Reconnect button visible.

export const Disconnected: Story = {
  render: () => ({
    components: { SSHTerminal },
    template: `
      <div style="width: 800px; height: 500px; background: #1a1b26;">
        <SSHTerminal host-id="main" />
      </div>
    `,
  }),
};

export const WithChatSession: Story = {
  render: () => ({
    components: { SSHTerminal },
    template: `
      <div style="width: 800px; height: 500px; background: #1a1b26;">
        <SSHTerminal host-id="frontend" chat-session-id="chat-session-abc-123" />
      </div>
    `,
  }),
};

export const NarrowViewport: Story = {
  render: () => ({
    components: { SSHTerminal },
    template: `
      <div style="width: 400px; height: 300px; background: #1a1b26;">
        <SSHTerminal host-id="main" />
      </div>
    `,
  }),
};

export const WideViewport: Story = {
  render: () => ({
    components: { SSHTerminal },
    template: `
      <div style="width: 1200px; height: 600px; background: #1a1b26;">
        <SSHTerminal host-id="ai-stack" />
      </div>
    `,
  }),
};
