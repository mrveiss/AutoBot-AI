// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import FilePathNavigation from './FilePathNavigation.vue';

const meta = {
  title: 'Components/FileBrowser/FilePathNavigation',
  component: FilePathNavigation,
  tags: ['autodocs'],
  argTypes: {
    currentPath: {
      control: 'text',
      description: 'Current filesystem path displayed as breadcrumb segments',
    },
    onNavigateToPath: { action: 'navigate-to-path' },
  },
} as Meta<typeof FilePathNavigation>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

export const Root: Story = {
  args: {
    currentPath: '/',
  },
};

export const SingleLevel: Story = {
  args: {
    currentPath: '/documents',
  },
};

export const DeepPath: Story = {
  args: {
    currentPath: '/home/user/projects/autobot/src',
  },
};

export const LogPath: Story = {
  args: {
    currentPath: '/var/log/autobot',
  },
};

export const LongPath: Story = {
  args: {
    currentPath: '/opt/autobot/autobot-frontend/src/components/file-browser',
  },
};
