// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import SourceManager from './SourceManager.vue';

const meta = {
  title: 'Components/Analytics/SourceManager',
  component: SourceManager,
  tags: ['autodocs'],
  argTypes: {
    visible: { control: 'boolean' },
    selectedSourceId: { control: 'text' },
  },
} as Meta<typeof SourceManager>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    visible: true,
    selectedSourceId: null,
  },
};

export const WithSelection: Story = {
  args: {
    visible: true,
    selectedSourceId: 'src-001',
  },
};

export const Hidden: Story = {
  args: {
    visible: false,
    selectedSourceId: null,
  },
};

export const Loading: Story = {
  args: {
    visible: true,
    selectedSourceId: null,
  },
};
