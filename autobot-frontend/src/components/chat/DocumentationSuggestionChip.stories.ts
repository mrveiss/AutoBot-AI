// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import DocumentationSuggestionChip from './DocumentationSuggestionChip.vue';

const meta = {
  title: 'Components/Chat/DocumentationSuggestionChip',
  component: DocumentationSuggestionChip,
  tags: ['autodocs'],
  argTypes: {
    label: {
      control: 'text',
      description: 'Chip label text',
    },
    category: {
      control: 'select',
      options: ['general', 'architecture', 'developer', 'api', 'guides', 'security'],
      description: 'Category for icon selection',
    },
    score: {
      control: { type: 'number', min: 0, max: 1, step: 0.01 },
      description: 'Relevance score',
    },
    isSelected: {
      control: 'boolean',
      description: 'Whether the chip is selected',
    },
    clickable: {
      control: 'boolean',
      description: 'Whether the chip is clickable',
    },
    dismissible: {
      control: 'boolean',
      description: 'Whether the chip has a dismiss button',
    },
    showScore: {
      control: 'boolean',
      description: 'Whether to show the relevance score',
    },
    maxLabelLength: {
      control: { type: 'number', min: 10, max: 100 },
      description: 'Maximum label length before truncation',
    },
  },
} as Meta<typeof DocumentationSuggestionChip>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<Record<string, unknown>>;

export const Default: Story = {
  args: {
    label: 'Composition API',
    category: 'developer',
    score: 0.88,
    isSelected: false,
    clickable: true,
    dismissible: false,
    showScore: false,
  },
};

export const Selected: Story = {
  args: {
    label: 'Architecture Overview',
    category: 'architecture',
    score: 0.95,
    isSelected: true,
    clickable: true,
    dismissible: false,
    showScore: true,
  },
};

export const Dismissible: Story = {
  args: {
    label: 'Redis Integration',
    category: 'developer',
    score: 0.72,
    isSelected: false,
    clickable: true,
    dismissible: true,
    showScore: true,
  },
};

export const LongLabel: Story = {
  args: {
    label: 'Very Long Documentation Topic Title That Should Be Truncated',
    category: 'guides',
    score: 0.60,
    isSelected: false,
    clickable: true,
    dismissible: false,
    showScore: false,
    maxLabelLength: 30,
  },
};
