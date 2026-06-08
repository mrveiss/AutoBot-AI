// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import ChatMessages from './ChatMessages.vue';

const meta = {
  title: 'Components/Chat/ChatMessages',
  component: ChatMessages,
  tags: ['autodocs'],
  parameters: {
    layout: 'fullscreen',
  },
} as Meta<typeof ChatMessages>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<any>;

export const Default: Story = {
  render: () => ({
    components: { ChatMessages },
    template: `<div style="height:600px; display:flex; flex-direction:column;"><ChatMessages /></div>`,
  }),
};

export const Contained: Story = {
  render: () => ({
    components: { ChatMessages },
    template: `<div style="height:500px; width:800px; overflow:hidden;"><ChatMessages /></div>`,
  }),
};
