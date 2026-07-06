// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import ChatSidebar from './ChatSidebar.vue';

const meta = {
  title: 'Components/Chat/ChatSidebar',
  component: ChatSidebar,
  tags: ['autodocs'],
  parameters: {
    layout: 'fullscreen',
  },
} as Meta<typeof ChatSidebar>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<Record<string, unknown>>;

export const Default: Story = {
  render: () => ({
    components: { ChatSidebar },
    template: `<div style="height:700px; width:320px; display:flex; overflow:hidden;"><ChatSidebar /></div>`,
  }),
};

export const MobileWidth: Story = {
  render: () => ({
    components: { ChatSidebar },
    template: `<div style="height:700px; width:280px; display:flex; overflow:hidden;"><ChatSidebar /></div>`,
  }),
};
