// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import MessageItem from './MessageItem.vue';

const meta = {
  title: 'Components/Chat/MessageItem',
  component: MessageItem,
  tags: ['autodocs'],
  argTypes: {
    message: {
      control: 'object',
      description: 'ChatMessage object to render',
    },
    isTyping: {
      control: 'boolean',
      description: 'Whether the assistant is currently streaming a response',
    },
    isLast: {
      control: 'boolean',
      description: 'Whether this is the last message in the list',
    },
    showJson: {
      control: 'boolean',
      description: 'Whether to show metadata JSON',
    },
    citationsExpanded: {
      control: 'boolean',
      description: 'Whether citations panel is expanded',
    },
    processingApproval: {
      control: 'boolean',
      description: 'Whether an approval action is being processed',
    },
  },
} as Meta<typeof MessageItem>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

const baseUserMessage = {
  id: 'msg-1',
  sender: 'user',
  content: 'Can you explain how Vue 3 reactivity works?',
  timestamp: new Date().toISOString(),
  status: 'sent',
};

const baseAssistantMessage = {
  id: 'msg-2',
  sender: 'assistant',
  content: 'Vue 3 uses a **Proxy-based** reactivity system. When you create a reactive object, Vue wraps it in a JavaScript Proxy that intercepts `get` and `set` operations.\n\nHere is a simple example:\n```js\nconst state = reactive({ count: 0 })\n```',
  timestamp: new Date().toISOString(),
  status: 'sent',
  metadata: { model: 'llama3', tokens: 120, duration: 843 },
};

export const UserMessage: Story = {
  args: {
    message: baseUserMessage,
    isTyping: false,
    isLast: false,
    showJson: false,
  },
};

export const AssistantMessage: Story = {
  args: {
    message: baseAssistantMessage,
    isTyping: false,
    isLast: true,
    showJson: false,
  },
};

export const AssistantWithMetadata: Story = {
  args: {
    message: baseAssistantMessage,
    isTyping: false,
    isLast: true,
    showJson: true,
  },
};

export const StreamingMessage: Story = {
  args: {
    message: {
      ...baseAssistantMessage,
      content: 'Vue 3 uses a Proxy-based...',
    },
    isTyping: true,
    isLast: true,
    showJson: false,
  },
};

export const ErrorMessage: Story = {
  args: {
    message: {
      id: 'msg-3',
      sender: 'user',
      content: 'Please retry this request',
      timestamp: new Date().toISOString(),
      status: 'error',
      error: 'Connection timeout after 30s',
    },
    isTyping: false,
    isLast: true,
  },
};

export const SystemMessage: Story = {
  args: {
    message: {
      id: 'msg-4',
      sender: 'system',
      content: 'Session started. Connected to AutoBot assistant.',
      timestamp: new Date().toISOString(),
      status: 'sent',
    },
    isTyping: false,
    isLast: false,
  },
};
