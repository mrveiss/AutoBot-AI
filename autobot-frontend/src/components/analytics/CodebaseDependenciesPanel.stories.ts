// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import CodebaseDependenciesPanel from './CodebaseDependenciesPanel.vue';

const sampleDependencyData = {
  nodes: [
    { id: 'mod_a', name: 'module_a', type: 'module' },
    { id: 'mod_b', name: 'module_b', type: 'module' },
    { id: 'mod_c', name: 'module_c', type: 'module' },
  ],
  edges: [
    { source: 'mod_a', target: 'mod_b', type: 'import' },
    { source: 'mod_b', target: 'mod_c', type: 'import' },
  ],
  summary: {
    total_modules: 3,
    total_import_relationships: 2,
    external_dependency_count: 5,
    circular_dependency_count: 0,
  },
};

const meta = {
  title: 'Components/Analytics/CodebaseDependenciesPanel',
  component: CodebaseDependenciesPanel,
  tags: ['autodocs'],
  argTypes: {
    dependencyLoading: { control: 'boolean' },
    dependencyError: { control: 'text' },
    importTreeLoading: { control: 'boolean' },
    importTreeError: { control: 'text' },
    callGraphLoading: { control: 'boolean' },
    callGraphError: { control: 'text' },
  },
} as Meta<typeof CodebaseDependenciesPanel>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    dependencyData: sampleDependencyData,
    dependencyLoading: false,
    dependencyError: '',
    importTreeData: [],
    importTreeLoading: false,
    importTreeError: '',
    callGraphData: { nodes: [], edges: [] },
    callGraphSummary: null,
    callGraphOrphaned: [],
    callGraphLoading: false,
    callGraphError: '',
  },
};

export const Loading: Story = {
  args: {
    dependencyData: null,
    dependencyLoading: true,
    dependencyError: '',
    importTreeData: [],
    importTreeLoading: true,
    importTreeError: '',
    callGraphData: { nodes: [], edges: [] },
    callGraphSummary: null,
    callGraphOrphaned: [],
    callGraphLoading: true,
    callGraphError: '',
  },
};

export const Error: Story = {
  args: {
    dependencyData: null,
    dependencyLoading: false,
    dependencyError: 'Failed to load dependency graph',
    importTreeData: [],
    importTreeLoading: false,
    importTreeError: 'Failed to load import tree',
    callGraphData: { nodes: [], edges: [] },
    callGraphSummary: null,
    callGraphOrphaned: [],
    callGraphLoading: false,
    callGraphError: '',
  },
};

export const Empty: Story = {
  args: {
    dependencyData: null,
    dependencyLoading: false,
    dependencyError: '',
    importTreeData: [],
    importTreeLoading: false,
    importTreeError: '',
    callGraphData: { nodes: [], edges: [] },
    callGraphSummary: null,
    callGraphOrphaned: [],
    callGraphLoading: false,
    callGraphError: '',
  },
};
