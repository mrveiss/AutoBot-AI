// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import MultiModelChat from './MultiModelChat.vue';

const meta = {
  title: 'Components/Chat/MultiModelChat',
  component: MultiModelChat,
  tags: ['autodocs'],
  argTypes: {},
} as Meta<typeof MultiModelChat>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {},
};
