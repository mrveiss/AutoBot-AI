// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import FilePreview from './FilePreview.vue';

const meta = {
  title: 'Components/FileBrowser/FilePreview',
  component: FilePreview,
  tags: ['autodocs'],
  argTypes: {
    showPreview: {
      control: 'boolean',
      description: 'Controls modal visibility',
    },
    previewFile: {
      control: 'object',
      description: 'FilePreviewData object with name, type, and optional url/content/size',
    },
    onClose: { action: 'close' },
    onDownload: { action: 'download' },
  },
} as Meta<typeof FilePreview>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

export const Hidden: Story = {
  args: {
    showPreview: false,
    previewFile: null,
  },
};

export const TextFile: Story = {
  args: {
    showPreview: true,
    previewFile: {
      name: 'readme.txt',
      type: 'text',
      content: 'This is a plain text file.\nIt has multiple lines.\nLine three here.',
    },
  },
};

export const JsonFile: Story = {
  args: {
    showPreview: true,
    previewFile: {
      name: 'config.json',
      type: 'json',
      content: '{"name":"autobot","version":"1.0.0","debug":false}',
    },
  },
};

export const ImageFile: Story = {
  args: {
    showPreview: true,
    previewFile: {
      name: 'logo.png',
      type: 'image',
      url: 'https://via.placeholder.com/400x300',
    },
  },
};

export const UnknownFile: Story = {
  args: {
    showPreview: true,
    previewFile: {
      name: 'archive.tar.gz',
      type: 'archive',
      fileType: 'GZ Archive',
      size: 2097152,
      url: '/files/archive.tar.gz',
    },
  },
};
