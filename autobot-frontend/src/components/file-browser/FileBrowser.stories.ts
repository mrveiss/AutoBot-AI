// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import FileBrowser from './FileBrowser.vue';

const meta = {
  title: 'Components/FileBrowser/FileBrowser',
  component: FileBrowser,
  tags: ['autodocs'],
  argTypes: {
    chatContext: {
      control: 'boolean',
      description: 'When true, logs file activity to the session activity logger',
    },
  },
} as Meta<typeof FileBrowser>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

export const Default: Story = {
  args: {
    chatContext: false,
  },
};

export const ChatContext: Story = {
  args: {
    chatContext: true,
  },
};

export const Standalone: Story = {
  render: () => ({
    components: { FileBrowser },
    template: `
      <div style="height: 600px; width: 100%;">
        <FileBrowser :chat-context="false" />
      </div>
    `,
  }),
};
