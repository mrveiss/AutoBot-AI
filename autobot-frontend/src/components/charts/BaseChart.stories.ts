// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import BaseChart from './BaseChart.vue';

const meta = {
  title: 'Components/Charts/BaseChart',
  component: BaseChart,
  tags: ['autodocs'],
  argTypes: {
    type: {
      control: 'select',
      options: ['line', 'area', 'bar', 'pie', 'donut', 'radialBar', 'scatter', 'bubble', 'heatmap', 'treemap', 'polarArea', 'radar'],
      description: 'ApexCharts chart type',
    },
    height: {
      control: 'text',
      description: 'Chart height (number or CSS string)',
    },
    width: {
      control: 'text',
      description: 'Chart width (number or CSS string)',
    },
    title: {
      control: 'text',
      description: 'Chart title',
    },
    subtitle: {
      control: 'text',
      description: 'Chart subtitle',
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
} as Meta<typeof BaseChart>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<any>;

export const BarChart: Story = {
  args: {
    type: 'bar',
    height: 350,
    title: 'Monthly Metrics',
    subtitle: 'Commits per month',
    series: [
      {
        name: 'Commits',
        data: [44, 55, 57, 56, 61, 58, 63, 60, 66],
      },
    ],
    options: {
      xaxis: {
        categories: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep'],
      },
    },
  },
};

export const LineChart: Story = {
  args: {
    type: 'line',
    height: 350,
    title: 'Code Quality Score',
    subtitle: 'Over time',
    series: [
      { name: 'Maintainability', data: [70, 74, 78, 75, 80, 83, 85] },
      { name: 'Complexity', data: [60, 58, 62, 65, 67, 70, 72] },
    ],
    options: {
      xaxis: {
        categories: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
      },
    },
  },
};

export const DonutChart: Story = {
  args: {
    type: 'donut',
    height: 350,
    title: 'Issue Distribution',
    subtitle: 'By severity',
    series: [44, 55, 13, 43],
    options: {
      labels: ['Critical', 'High', 'Medium', 'Low'],
    },
  },
};

export const LoadingState: Story = {
  args: {
    type: 'bar',
    height: 350,
    title: 'Loading Chart',
    series: [],
    loading: true,
  },
};

export const ErrorState: Story = {
  args: {
    type: 'bar',
    height: 350,
    title: 'Error Chart',
    series: [],
    error: 'Failed to load chart data. Please try again.',
  },
};

export const NoDataState: Story = {
  args: {
    type: 'bar',
    height: 350,
    title: 'Empty Chart',
    series: [],
  },
};
