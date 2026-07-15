// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import AccessMetrics from './AccessMetrics.vue';

const meta = {
  title: 'Components/FeatureFlags/AccessMetrics',
  component: AccessMetrics,
  tags: ['autodocs'],
  argTypes: {
    metrics: {
      control: 'object',
      description: 'ViolationStatistics object or null',
    },
    loading: {
      control: 'boolean',
      description: 'Show loading state',
    },
    compact: {
      control: 'boolean',
      description: 'Compact display mode (summary cards only, no breakdowns)',
    },
  },
} as Meta<typeof AccessMetrics>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

const sampleMetrics = {
  total_violations: 47,
  period_days: 7,
  daily_change_percent: 12.5,
  by_endpoint: {
    '/api/admin/users': 18,
    '/api/settings/global': 14,
    '/api/agent/config': 9,
    '/api/knowledge/delete': 6,
  },
  by_user: {
    'alice@example.com': 22,
    'bob@example.com': 15,
    'charlie@example.com': 10,
  },
  by_day: {
    '2026-05-10': 5,
    '2026-05-11': 8,
    '2026-05-12': 4,
    '2026-05-13': 11,
    '2026-05-14': 7,
    '2026-05-15': 9,
    '2026-05-16': 3,
  },
  recent_violations: [
    {
      id: 'v1',
      timestamp: Math.floor(Date.now() / 1000) - 300,
      username: 'alice@example.com',
      endpoint: '/api/admin/users',
      actual_owner: 'admin',
    },
    {
      id: 'v2',
      timestamp: Math.floor(Date.now() / 1000) - 900,
      username: 'bob@example.com',
      endpoint: '/api/settings/global',
      actual_owner: 'superadmin',
    },
    {
      id: 'v3',
      timestamp: Math.floor(Date.now() / 1000) - 3600,
      username: 'charlie@example.com',
      endpoint: '/api/agent/config',
      actual_owner: 'admin',
    },
  ],
};

export const WithData: Story = {
  args: {
    metrics: sampleMetrics,
    loading: false,
    compact: false,
  },
};

export const CompactMode: Story = {
  args: {
    metrics: sampleMetrics,
    loading: false,
    compact: true,
  },
};

export const Loading: Story = {
  args: {
    metrics: null,
    loading: true,
    compact: false,
  },
};

export const NoViolations: Story = {
  args: {
    metrics: {
      total_violations: 0,
      period_days: 7,
      daily_change_percent: -100,
      by_endpoint: {},
      by_user: {},
      by_day: {},
      recent_violations: [],
    },
    loading: false,
    compact: false,
  },
};

export const TrendDown: Story = {
  args: {
    metrics: {
      ...sampleMetrics,
      daily_change_percent: -25.3,
    },
    loading: false,
    compact: false,
  },
};
