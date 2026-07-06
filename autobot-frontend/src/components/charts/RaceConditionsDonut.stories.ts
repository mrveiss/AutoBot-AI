// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import RaceConditionsDonut from './RaceConditionsDonut.vue';

const meta = {
  title: 'Components/Charts/RaceConditionsDonut',
  component: RaceConditionsDonut,
  tags: ['autodocs'],
  argTypes: {
    title: {
      control: 'text',
      description: 'Chart title (overrides i18n default)',
    },
    subtitle: {
      control: 'text',
      description: 'Chart subtitle',
    },
    height: {
      control: 'number',
      description: 'Chart height in pixels',
    },
    loading: {
      control: 'boolean',
      description: 'Show loading state',
    },
    error: {
      control: 'text',
      description: 'Error message to display',
    },
  },
} as Meta<typeof RaceConditionsDonut>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<Record<string, unknown>>;

const sampleData = [
  { category: 'thread_unsafe_singleton', count: 7 },
  { category: 'unprotected_global_state', count: 12 },
  { category: 'async_shared_state', count: 9 },
  { category: 'file_write_without_lock', count: 4 },
  { category: 'read_modify_write', count: 6 },
];

export const Default: Story = {
  args: {
    data: sampleData,
    height: 350,
  },
};

export const WithCustomTitle: Story = {
  args: {
    data: sampleData,
    title: 'Race Condition Breakdown',
    subtitle: 'Detected concurrency issues by category',
    height: 350,
  },
};

export const NameValueFormat: Story = {
  args: {
    data: [
      { name: 'thread_unsafe_singleton', value: 5 },
      { name: 'async_global_modification', value: 8 },
      { name: 'unprotected_mutating_method', value: 3 },
    ],
    title: 'Race Conditions (name/value format)',
    height: 350,
  },
};

export const LoadingState: Story = {
  args: {
    data: [],
    loading: true,
    height: 350,
  },
};

export const ErrorState: Story = {
  args: {
    data: [],
    error: 'Failed to load race condition data.',
    height: 350,
  },
};
