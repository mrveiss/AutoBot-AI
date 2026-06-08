// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import ShareConversationDialog from './ShareConversationDialog.vue';

const meta = {
  title: 'Components/Chat/ShareConversationDialog',
  component: ShareConversationDialog,
  tags: ['autodocs'],
  argTypes: {
    visible: {
      control: 'boolean',
      description: 'Whether the dialog is visible',
    },
    sessionId: {
      control: 'text',
      description: 'Chat session ID to share',
    },
  },
} as Meta<typeof ShareConversationDialog>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    visible: true,
    sessionId: 'session-abc-123',
  },
};

export const Hidden: Story = {
  args: {
    visible: false,
    sessionId: 'session-abc-123',
  },
};
