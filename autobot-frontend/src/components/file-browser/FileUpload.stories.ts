// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import FileUpload from './FileUpload.vue';
import { createLogger } from '@/utils/debugUtils';

const logger = createLogger('FileUploadStory');

const meta = {
  title: 'Components/FileBrowser/FileUpload',
  component: FileUpload,
  tags: ['autodocs'],
  argTypes: {
    onFilesSelected: { action: 'files-selected' },
  },
} as Meta<typeof FileUpload>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {};

export const InlineUsage: Story = {
  render: () => ({
    components: { FileUpload },
    template: `
      <div style="padding: 16px; background: #f9f9f9; border-radius: 8px;">
        <p style="margin-bottom: 8px; font-size: 14px; color: #666;">Inline file upload:</p>
        <FileUpload @files-selected="onFilesSelected" />
      </div>
    `,
    methods: {
      onFilesSelected(files: FileList) {
        logger.info('Files selected:', Array.from(files).map(f => f.name));
      },
    },
  }),
};

export const FullWidth: Story = {
  render: () => ({
    components: { FileUpload },
    template: `
      <div style="width: 100%; max-width: 600px;">
        <FileUpload @files-selected="() => {}" />
      </div>
    `,
  }),
};

export const Compact: Story = {
  render: () => ({
    components: { FileUpload },
    template: `
      <div style="width: 300px;">
        <FileUpload @files-selected="() => {}" />
      </div>
    `,
  }),
};
