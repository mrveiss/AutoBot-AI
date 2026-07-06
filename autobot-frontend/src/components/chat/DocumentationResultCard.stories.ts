// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import DocumentationResultCard from './DocumentationResultCard.vue';

const meta = {
  title: 'Components/Chat/DocumentationResultCard',
  component: DocumentationResultCard,
  tags: ['autodocs'],
  argTypes: {
    title: {
      control: 'text',
      description: 'Document title',
    },
    content: {
      control: 'text',
      description: 'Document content/excerpt',
    },
    category: {
      control: 'select',
      options: ['general', 'architecture', 'developer', 'api', 'guides', 'security'],
      description: 'Document category',
    },
    score: {
      control: { type: 'number', min: 0, max: 1, step: 0.01 },
      description: 'Relevance score (0-1)',
    },
    isHighlighted: {
      control: 'boolean',
      description: 'Highlight the card as the top result',
    },
    maxContentLength: {
      control: { type: 'number', min: 100, max: 1000 },
      description: 'Max content characters before truncation',
    },
  },
} as Meta<typeof DocumentationResultCard>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<Record<string, unknown>>;

export const Default: Story = {
  args: {
    title: 'Vue 3 Composition API Overview',
    content: 'The Composition API is a set of APIs that allows us to author Vue components using imported functions instead of declaring options. It encompasses the Reactivity API, Lifecycle Hooks, and Dependency Injection.',
    category: 'developer',
    filePath: 'docs/frontend/vue-composition-api.md',
    score: 0.94,
    isHighlighted: false,
    maxContentLength: 300,
  },
};

export const Highlighted: Story = {
  args: {
    title: 'AutoBot Architecture Overview',
    content: 'AutoBot is a multi-agent AI automation platform built on FastAPI (backend), Vue 3 (frontend), and a distributed worker system for NPU/GPU task execution.',
    category: 'architecture',
    filePath: 'docs/architecture/overview.md',
    score: 0.98,
    isHighlighted: true,
    maxContentLength: 300,
  },
};

export const LongContent: Story = {
  args: {
    title: 'Redis Integration Patterns',
    content: 'Redis is used throughout AutoBot for multiple purposes: caching, pub/sub messaging between workers, session storage, and as a coordination layer for distributed leader election. The recommended pattern is to use get_async_redis_client() which returns an Optional[Redis] — always guard against None before use.',
    category: 'developer',
    filePath: 'docs/backend/redis-patterns.md',
    score: 0.81,
    isHighlighted: false,
    maxContentLength: 150,
  },
};
