// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import SeverityBarChart from './SeverityBarChart.vue';

const meta = {
  title: 'Components/Charts/SeverityBarChart',
  component: SeverityBarChart,
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
} as Meta<typeof SeverityBarChart>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<Record<string, unknown>>;

const sampleData = [
  { severity: 'critical', count: 5 },
  { severity: 'high', count: 18 },
  { severity: 'medium', count: 43 },
  { severity: 'low', count: 87 },
  { severity: 'info', count: 124 },
];

export const Default: Story = {
  args: {
    data: sampleData,
    height: 300,
  },
};

export const WithCustomTitle: Story = {
  args: {
    data: sampleData,
    title: 'Issues by Severity',
    subtitle: 'Count of detected problems per severity level',
    height: 300,
  },
};

export const NameValueFormat: Story = {
  args: {
    data: [
      { name: 'error', value: 8 },
      { name: 'warning', value: 34 },
      { name: 'hint', value: 61 },
    ],
    title: 'Severity Levels (name/value format)',
    height: 250,
  },
};

export const HighSeverityOnly: Story = {
  args: {
    data: [
      { severity: 'critical', count: 3 },
      { severity: 'high', count: 9 },
    ],
    title: 'High Severity Issues',
    height: 200,
  },
};

export const LoadingState: Story = {
  args: {
    data: [],
    loading: true,
    height: 300,
  },
};
