// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import EvolutionTimelineChart from './EvolutionTimelineChart.vue';

const meta = {
  title: 'Components/Charts/EvolutionTimelineChart',
  component: EvolutionTimelineChart,
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
    metrics: {
      control: 'object',
      description: 'Metrics to display from timeline data',
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
} as Meta<typeof EvolutionTimelineChart>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<Record<string, unknown>>;

function makeDays(count: number) {
  const now = Date.now();
  return Array.from({ length: count }, (_, i) => {
    const d = new Date(now - (count - 1 - i) * 86400000);
    return d.toISOString();
  });
}

const timestamps = makeDays(14);

const sampleData = timestamps.map((timestamp, i) => ({
  timestamp,
  overall_score: 60 + i * 1.5 + Math.sin(i) * 3,
  maintainability: 55 + i * 1.2 + Math.cos(i) * 4,
  complexity: 70 - i * 0.8 + Math.sin(i * 0.7) * 2,
}));

export const Default: Story = {
  args: {
    data: sampleData,
    height: 400,
  },
};

export const WithCustomTitle: Story = {
  args: {
    data: sampleData,
    title: 'Code Health Over 2 Weeks',
    subtitle: 'Overall score, maintainability and complexity',
    height: 400,
  },
};

export const AllMetrics: Story = {
  args: {
    data: sampleData.map((d, i) => ({
      ...d,
      testability: 50 + i * 1.8,
      security: 80 - i * 0.5,
      performance: 65 + i,
    })),
    metrics: ['overall_score', 'maintainability', 'complexity', 'testability', 'security', 'performance'],
    height: 450,
    title: 'All Quality Metrics',
  },
};

export const LoadingState: Story = {
  args: {
    data: [],
    loading: true,
    height: 400,
  },
};

export const EmptyData: Story = {
  args: {
    data: [],
    title: 'No Evolution Data',
    height: 400,
  },
};
