// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import TreeNodeComponent from './TreeNodeComponent.vue'

const meta = {
  title: 'Components/Knowledge/TreeNodeComponent',
  component: TreeNodeComponent,
  tags: ['autodocs'],
  argTypes: {
    node: { control: 'object' },
    expandedNodes: { control: 'object' },
    selectedId: { control: 'text' },
    selectedDocuments: { control: 'object' },
    vectorizationStates: { control: 'object' },
  },
} as Meta<typeof TreeNodeComponent>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

const fileNode = {
  id: 'file-1',
  name: 'README.md',
  type: 'file',
  path: '/docs/README.md',
  size: 2048,
  date: '2026-05-01',
}

const folderNode = {
  id: 'folder-1',
  name: 'Documentation',
  type: 'folder',
  path: '/docs',
  children: [
    { id: 'file-1', name: 'README.md', type: 'file', path: '/docs/README.md', size: 2048 },
    { id: 'file-2', name: 'SETUP.md', type: 'file', path: '/docs/SETUP.md', size: 4096 },
  ],
}

export const File: Story = {
  args: {
    node: fileNode,
    expandedNodes: new Set<string>(),
    selectedId: undefined,
    selectedDocuments: new Set<string>(),
    vectorizationStates: new Map(),
  },
}

export const FileSelected: Story = {
  args: {
    node: fileNode,
    expandedNodes: new Set<string>(),
    selectedId: 'file-1',
    selectedDocuments: new Set(['file-1']),
    vectorizationStates: new Map([['file-1', { status: 'vectorized' }]]),
  },
}

export const FolderCollapsed: Story = {
  args: {
    node: folderNode,
    expandedNodes: new Set<string>(),
    selectedId: undefined,
    selectedDocuments: new Set<string>(),
    vectorizationStates: new Map(),
  },
}

export const FolderExpanded: Story = {
  args: {
    node: folderNode,
    expandedNodes: new Set(['folder-1']),
    selectedId: undefined,
    selectedDocuments: new Set<string>(),
    vectorizationStates: new Map(),
  },
}

export const FileWithVectorizationFailed: Story = {
  args: {
    node: fileNode,
    expandedNodes: new Set<string>(),
    selectedId: undefined,
    selectedDocuments: new Set<string>(),
    vectorizationStates: new Map([['file-1', { status: 'failed' }]]),
  },
}
