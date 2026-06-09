// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import DependencyTreemap from './DependencyTreemap.vue';

const meta = {
  title: 'Components/Charts/DependencyTreemap',
  component: DependencyTreemap,
  tags: ['autodocs'],
  argTypes: {
    title: {
      control: 'text',
      description: 'Chart title (overrides i18n default)',
    },
    subtitle: {
      control: 'text',
      description: 'Chart subtitle (overrides i18n default)',
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
} as Meta<typeof DependencyTreemap>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<any>;

const sampleData = [
  { package: 'fastapi', usage_count: 87 },
  { package: 'pydantic', usage_count: 64 },
  { package: 'sqlalchemy', usage_count: 52 },
  { package: 'redis', usage_count: 45 },
  { package: 'httpx', usage_count: 38 },
  { package: 'celery', usage_count: 29 },
  { package: 'pytest', usage_count: 23 },
  { package: 'numpy', usage_count: 18 },
  { package: 'boto3', usage_count: 14 },
  { package: 'jwt', usage_count: 11 },
];

export const Default: Story = {
  args: {
    data: sampleData,
    height: 400,
  },
};

export const WithCustomTitle: Story = {
  args: {
    data: sampleData,
    title: 'Python Package Usage',
    subtitle: 'Top external dependencies by import count',
    height: 400,
  },
};

export const SmallDataset: Story = {
  args: {
    data: sampleData.slice(0, 4),
    title: 'Top 4 Dependencies',
    height: 300,
  },
};

export const LoadingState: Story = {
  args: {
    data: [],
    loading: true,
    height: 400,
  },
};

export const ErrorState: Story = {
  args: {
    data: [],
    error: 'Failed to load dependency data.',
    height: 400,
  },
};
