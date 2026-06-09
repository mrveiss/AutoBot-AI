// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import FileTreeView from './FileTreeView.vue';

const flatTree = [
  { name: 'home', path: '/home', is_dir: true, level: 0, expanded: true },
  { name: 'user', path: '/home/user', is_dir: true, level: 1, expanded: true },
  { name: 'documents', path: '/home/user/documents', is_dir: true, level: 2, expanded: false },
  { name: 'notes.txt', path: '/home/user/notes.txt', is_dir: false, level: 2 },
  { name: 'projects', path: '/home/user/projects', is_dir: true, level: 2, expanded: true },
  { name: 'autobot', path: '/home/user/projects/autobot', is_dir: true, level: 3, expanded: false },
];

const meta = {
  title: 'Components/FileBrowser/FileTreeView',
  component: FileTreeView,
  tags: ['autodocs'],
  argTypes: {
    directoryTree: {
      control: 'object',
      description: 'Flat array of TreeItem nodes representing the directory structure',
    },
    selectedPath: {
      control: 'text',
      description: 'Path of the currently selected tree node',
    },
    onToggleNode: { action: 'toggle-node' },
    onExpandAll: { action: 'expand-all' },
    onCollapseAll: { action: 'collapse-all' },
  },
} as Meta<typeof FileTreeView>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    directoryTree: flatTree,
    selectedPath: '/home/user',
  },
};

export const Empty: Story = {
  args: {
    directoryTree: [],
    selectedPath: '',
  },
};

export const SingleLevel: Story = {
  args: {
    directoryTree: [
      { name: 'documents', path: '/documents', is_dir: true, level: 0, expanded: false },
      { name: 'images', path: '/images', is_dir: true, level: 0, expanded: false },
      { name: 'logs', path: '/logs', is_dir: true, level: 0, expanded: false },
    ],
    selectedPath: '/documents',
  },
};

export const DeepSelection: Story = {
  args: {
    directoryTree: flatTree,
    selectedPath: '/home/user/projects/autobot',
  },
};

export const AllExpanded: Story = {
  args: {
    directoryTree: flatTree.map(node => ({ ...node, expanded: true })),
    selectedPath: '/home/user/documents',
  },
};
