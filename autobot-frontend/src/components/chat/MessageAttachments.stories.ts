// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import MessageAttachments from './MessageAttachments.vue';

const meta = {
  title: 'Components/Chat/MessageAttachments',
  component: MessageAttachments,
  tags: ['autodocs'],
  argTypes: {
    attachments: {
      control: 'object',
      description: 'List of attachment objects to display',
    },
  },
} as Meta<typeof MessageAttachments>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

export const Default: Story = {
  args: {
    attachments: [
      { id: '1', name: 'report.pdf', type: 'application/pdf', size: 204800 },
      { id: '2', name: 'screenshot.png', type: 'image/png', size: 51200 },
    ],
  },
};

export const SingleDocument: Story = {
  args: {
    attachments: [
      { id: '1', name: 'project-spec.docx', type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', size: 153600 },
    ],
  },
};

export const MixedTypes: Story = {
  args: {
    attachments: [
      { id: '1', name: 'data.csv', type: 'text/csv', size: 8192 },
      { id: '2', name: 'video.mp4', type: 'video/mp4', size: 10485760 },
      { id: '3', name: 'archive.zip', type: 'application/zip', size: 2097152 },
      { id: '4', name: 'script.py', type: 'text/x-python', size: 4096 },
    ],
  },
};

export const Empty: Story = {
  args: {
    attachments: [],
  },
};
