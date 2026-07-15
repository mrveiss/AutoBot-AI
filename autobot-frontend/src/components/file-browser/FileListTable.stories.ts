// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import FileListTable from './FileListTable.vue';

const sampleFiles = [
  { name: 'documents', path: '/documents', is_dir: true, last_modified: '2026-05-01T10:00:00Z' },
  { name: 'images', path: '/images', is_dir: true, last_modified: '2026-05-10T08:30:00Z' },
  { name: 'report.pdf', path: '/report.pdf', is_dir: false, size: 204800, last_modified: '2026-05-12T14:22:00Z' },
  { name: 'config.json', path: '/config.json', is_dir: false, size: 1024, last_modified: '2026-04-30T09:15:00Z' },
  { name: 'main.ts', path: '/main.ts', is_dir: false, size: 3512, last_modified: '2026-05-15T17:45:00Z' },
];

const meta = {
  title: 'Components/FileBrowser/FileListTable',
  component: FileListTable,
  tags: ['autodocs'],
  argTypes: {
    files: {
      control: 'object',
      description: 'Array of FileItem objects to display in the table',
    },
    sortField: {
      control: 'select',
      options: ['name', 'type', 'size', 'modified'],
      description: 'Field currently used for sorting',
    },
    sortOrder: {
      control: 'select',
      options: ['asc', 'desc'],
      description: 'Sort direction',
    },
    currentPath: {
      control: 'text',
      description: 'Current directory path',
    },
    onSort: { action: 'sort' },
    onNavigate: { action: 'navigate' },
    onViewFile: { action: 'view-file' },
    onRenameFile: { action: 'rename-file' },
    onDeleteFile: { action: 'delete-file' },
  },
} as Meta<typeof FileListTable>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

export const Default: Story = {
  args: {
    files: sampleFiles,
    sortField: 'name',
    sortOrder: 'asc',
    currentPath: '/',
  },
};

export const SortedBySize: Story = {
  args: {
    files: sampleFiles,
    sortField: 'size',
    sortOrder: 'desc',
    currentPath: '/',
  },
};

export const SortedByModified: Story = {
  args: {
    files: sampleFiles,
    sortField: 'modified',
    sortOrder: 'asc',
    currentPath: '/documents',
  },
};

export const Empty: Story = {
  args: {
    files: [],
    sortField: 'name',
    sortOrder: 'asc',
    currentPath: '/empty-folder',
  },
};

export const FilesOnly: Story = {
  args: {
    files: [
      { name: 'archive.zip', path: '/archive.zip', is_dir: false, size: 1048576, last_modified: '2026-05-01T00:00:00Z' },
      { name: 'photo.png', path: '/photo.png', is_dir: false, size: 524288, last_modified: '2026-05-08T12:00:00Z' },
      { name: 'notes.txt', path: '/notes.txt', is_dir: false, size: 256, last_modified: '2026-05-14T18:00:00Z' },
    ],
    sortField: 'name',
    sortOrder: 'asc',
    currentPath: '/',
  },
};
