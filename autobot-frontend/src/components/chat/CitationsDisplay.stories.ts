// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import CitationsDisplay from './CitationsDisplay.vue';

const sampleCitations = [
  {
    id: 'cit-001',
    title: 'Vue 3 Composition API Guide',
    content: 'The Composition API is a set of APIs that allows us to author Vue components using imported functions instead of declaring options.',
    source: 'https://vuejs.org/guide/extras/composition-api-faq.html',
    score: 0.92,
  },
  {
    id: 'cit-002',
    title: 'Pinia State Management',
    content: 'Pinia is the recommended state management library for Vue applications. It is intuitive, type safe, and has devtools support.',
    source: 'https://pinia.vuejs.org/introduction.html',
    score: 0.85,
  },
  {
    id: 'cit-003',
    title: 'Vite Build Tool',
    content: 'Vite is a modern frontend build tool that provides an extremely fast development experience for modern web projects.',
    source: 'https://vitejs.dev/guide/',
    score: 0.78,
  },
];

const meta = {
  title: 'Components/Chat/CitationsDisplay',
  component: CitationsDisplay,
  tags: ['autodocs'],
  argTypes: {
    maxLength: {
      control: { type: 'number', min: 50, max: 500 },
      description: 'Maximum content length before truncation',
    },
    initiallyExpanded: {
      control: 'boolean',
      description: 'Whether citations are expanded on mount',
    },
  },
} as Meta<typeof CitationsDisplay>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<any>;

export const Collapsed: Story = {
  args: {
    citations: sampleCitations,
    maxLength: 200,
    initiallyExpanded: false,
  },
};

export const Expanded: Story = {
  args: {
    citations: sampleCitations,
    maxLength: 200,
    initiallyExpanded: true,
  },
};

export const SingleCitation: Story = {
  args: {
    citations: [sampleCitations[0]],
    maxLength: 300,
    initiallyExpanded: true,
  },
};

export const Empty: Story = {
  args: {
    citations: [],
    initiallyExpanded: false,
  },
};
