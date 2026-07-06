// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import TypingIndicator from './TypingIndicator.vue';

const meta = {
  title: 'Components/Chat/TypingIndicator',
  component: TypingIndicator,
  tags: ['autodocs'],
  argTypes: {
    isTyping: {
      control: 'boolean',
      description: 'Whether the AI is currently generating a response',
    },
    messageComplexity: {
      control: 'number',
      description: 'Estimated complexity of the response (0–100+), used to compute ETA',
    },
    streamingPreview: {
      control: 'text',
      description: 'Live content snippet from the LLM stream to display instead of placeholder text',
    },
  },
} as Meta<typeof TypingIndicator>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

export const Default: Story = {
  args: {
    isTyping: true,
    messageComplexity: 0,
    streamingPreview: '',
  },
};

export const WithStreamingPreview: Story = {
  args: {
    isTyping: true,
    messageComplexity: 40,
    streamingPreview: 'Vue 3 uses a Proxy-based reactivity system...',
  },
};

export const HighComplexity: Story = {
  args: {
    isTyping: true,
    messageComplexity: 500,
    streamingPreview: '',
  },
};

export const NotTyping: Story = {
  args: {
    isTyping: false,
    messageComplexity: 0,
    streamingPreview: '',
  },
};
