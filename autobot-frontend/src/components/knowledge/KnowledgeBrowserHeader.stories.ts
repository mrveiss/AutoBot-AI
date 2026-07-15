// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import KnowledgeBrowserHeader from './KnowledgeBrowserHeader.vue'

const meta = {
  title: 'Components/Knowledge/KnowledgeBrowserHeader',
  component: KnowledgeBrowserHeader,
  tags: ['autodocs'],
  argTypes: {
    categories: { control: 'object' },
    selectedCategory: { control: 'text' },
    searchQuery: { control: 'text' },
  },
} as Meta<typeof KnowledgeBrowserHeader>

export default meta
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>

export const Default: Story = {
  args: {
    categories: [
      { value: null, label: 'All', icon: 'fas fa-th', count: 42 },
      { value: 'system', label: 'System', icon: 'fas fa-cogs', count: 15 },
      { value: 'user', label: 'User', icon: 'fas fa-user', count: 27 },
    ],
    selectedCategory: null,
    searchQuery: '',
  },
}

export const WithActiveCategory: Story = {
  args: {
    categories: [
      { value: null, label: 'All', icon: 'fas fa-th', count: 42 },
      { value: 'system', label: 'System', icon: 'fas fa-cogs', count: 15 },
      { value: 'user', label: 'User', icon: 'fas fa-user', count: 27 },
    ],
    selectedCategory: 'system',
    searchQuery: '',
  },
}

export const WithSearch: Story = {
  args: {
    categories: [
      { value: null, label: 'All', icon: 'fas fa-th', count: 42 },
      { value: 'system', label: 'System', icon: 'fas fa-cogs', count: 15 },
    ],
    selectedCategory: null,
    searchQuery: 'autobot config',
  },
}

export const EmptyCategories: Story = {
  args: {
    categories: [],
    selectedCategory: null,
    searchQuery: '',
  },
}
