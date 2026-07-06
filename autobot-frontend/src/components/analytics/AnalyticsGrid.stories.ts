// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import AnalyticsGrid from './AnalyticsGrid.vue';

const meta = {
  title: 'Components/Analytics/AnalyticsGrid',
  component: AnalyticsGrid,
  tags: ['autodocs'],
  argTypes: {
    realTimeEnabled: { control: 'boolean' },
    systemOverview: { control: 'object' },
    communicationPatterns: { control: 'object' },
    codeQuality: { control: 'object' },
    performanceMetrics: { control: 'object' },
  },
} as Meta<typeof AnalyticsGrid>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

export const Default: Story = {
  args: {
    systemOverview: {
      api_requests_per_minute: 35,
      average_response_time: 150,
      active_connections: 5,
      system_health: 'Healthy',
    },
    communicationPatterns: {
      websocket_connections: 2,
      api_call_frequency: 8,
      data_transfer_rate: 18.3,
    },
    codeQuality: {
      overall_score: 79,
      test_coverage: 58,
      code_duplicates: 22,
      technical_debt: 12,
    },
    performanceMetrics: {
      efficiency_score: 85,
      memory_usage: 480,
      cpu_usage: 18,
      load_time: 290,
    },
    realTimeEnabled: true,
  },
};

export const Empty: Story = {
  args: {
    systemOverview: null,
    communicationPatterns: null,
    codeQuality: null,
    performanceMetrics: null,
    realTimeEnabled: false,
  },
};

export const StaticMode: Story = {
  args: {
    systemOverview: {
      api_requests_per_minute: 0,
      average_response_time: 0,
      active_connections: 0,
      system_health: 'Degraded',
    },
    communicationPatterns: null,
    codeQuality: null,
    performanceMetrics: null,
    realTimeEnabled: false,
  },
};
