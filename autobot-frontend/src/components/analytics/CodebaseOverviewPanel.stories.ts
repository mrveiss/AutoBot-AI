// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import CodebaseOverviewPanel from './CodebaseOverviewPanel.vue';

const meta = {
  title: 'Components/Analytics/CodebaseOverviewPanel',
  component: CodebaseOverviewPanel,
  tags: ['autodocs'],
  argTypes: {
    realTimeEnabled: { control: 'boolean' },
    systemOverview: { control: 'object' },
    communicationPatterns: { control: 'object' },
    codeQuality: { control: 'object' },
    performanceMetrics: { control: 'object' },
  },
} as Meta<typeof CodebaseOverviewPanel>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

export const Default: Story = {
  args: {
    systemOverview: {
      api_requests_per_minute: 42,
      average_response_time: 180,
      active_connections: 7,
      system_health: 'Healthy',
    },
    communicationPatterns: {
      websocket_connections: 3,
      api_call_frequency: 12,
      data_transfer_rate: 24.5,
      unique_endpoints: 18,
    },
    codeQuality: {
      overall_score: 84,
      test_coverage: 67,
      code_duplicates: 12,
      technical_debt: 8,
    },
    performanceMetrics: {
      efficiency_score: 91,
      memory_usage: 512,
      cpu_usage: 23,
      load_time: 340,
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

export const StaticData: Story = {
  args: {
    systemOverview: {
      api_requests_per_minute: 0,
      average_response_time: 0,
      active_connections: 0,
      system_health: 'Unknown',
    },
    communicationPatterns: null,
    codeQuality: {
      overall_score: 55,
      test_coverage: 30,
      code_duplicates: 45,
      technical_debt: 40,
    },
    performanceMetrics: null,
    realTimeEnabled: false,
  },
};
