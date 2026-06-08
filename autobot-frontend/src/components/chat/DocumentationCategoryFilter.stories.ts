// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import DocumentationCategoryFilter from './DocumentationCategoryFilter.vue';

const sampleCategories = [
  { id: 'architecture', name: 'Architecture', count: 24 },
  { id: 'developer', name: 'Developer', count: 18 },
  { id: 'api', name: 'API Reference', count: 42 },
  { id: 'guides', name: 'Guides', count: 11 },
  { id: 'security', name: 'Security', count: 7 },
];

const meta = {
  title: 'Components/Chat/DocumentationCategoryFilter',
  component: DocumentationCategoryFilter,
  tags: ['autodocs'],
  argTypes: {
    isLoading: {
      control: 'boolean',
      description: 'Loading state',
    },
    multiSelect: {
      control: 'boolean',
      description: 'Allow multiple category selection',
    },
    error: {
      control: 'text',
      description: 'Error message to display',
    },
  },
} as Meta<typeof DocumentationCategoryFilter>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    categories: sampleCategories,
    selectedCategories: [],
    isLoading: false,
    multiSelect: true,
  },
};

export const WithSelection: Story = {
  args: {
    categories: sampleCategories,
    selectedCategories: ['architecture', 'developer'],
    isLoading: false,
    multiSelect: true,
  },
};

export const Loading: Story = {
  args: {
    categories: [],
    selectedCategories: [],
    isLoading: true,
    multiSelect: true,
  },
};

export const WithError: Story = {
  args: {
    categories: [],
    selectedCategories: [],
    isLoading: false,
    error: 'Failed to load categories. Please try again.',
    multiSelect: true,
  },
};
