// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import CodebaseSecurityPanel from './CodebaseSecurityPanel.vue';

const meta = {
  title: 'Components/Analytics/CodebaseSecurityPanel',
  component: CodebaseSecurityPanel,
  tags: ['autodocs'],
  argTypes: {
    securityFindings: { control: 'object' },
    performanceFindings: { control: 'object' },
    redisFindings: { control: 'object' },
    findingsLoading: { control: 'boolean' },
    analysisLoading: { control: 'boolean' },
    totalFindings: { control: 'number' },
  },
} as Meta<typeof CodebaseSecurityPanel>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    securityFindings: [
      {
        id: 'sec-001',
        file_path: 'autobot-backend/api/routes.py',
        line_number: 42,
        severity: 'high',
        pattern_name: 'SQL Injection Risk',
        description: 'Unsanitized user input used in query',
        suggestion: 'Use parameterized queries',
      },
    ],
    performanceFindings: [],
    redisFindings: [],
    findingsLoading: false,
    analysisLoading: false,
    totalFindings: 1,
  },
};

export const Loading: Story = {
  args: {
    securityFindings: [],
    performanceFindings: [],
    redisFindings: [],
    findingsLoading: true,
    analysisLoading: true,
    totalFindings: 0,
  },
};

export const Empty: Story = {
  args: {
    securityFindings: [],
    performanceFindings: [],
    redisFindings: [],
    findingsLoading: false,
    analysisLoading: false,
    totalFindings: 0,
  },
};

export const MultipleFindings: Story = {
  args: {
    securityFindings: [
      {
        id: 'sec-001',
        file_path: 'autobot-backend/api/routes.py',
        line_number: 42,
        severity: 'critical',
        pattern_name: 'Hardcoded Secret',
        description: 'API key hardcoded in source',
        suggestion: 'Move to environment variable',
      },
      {
        id: 'sec-002',
        file_path: 'autobot-backend/auth/handler.py',
        line_number: 15,
        severity: 'high',
        pattern_name: 'Weak Hash',
        description: 'MD5 used for password hashing',
        suggestion: 'Use bcrypt or argon2',
      },
    ],
    performanceFindings: [
      {
        id: 'perf-001',
        file_path: 'autobot-backend/db/queries.py',
        line_number: 88,
        severity: 'medium',
        pattern_name: 'N+1 Query',
        description: 'Database query in loop',
        suggestion: 'Use batch query',
      },
    ],
    redisFindings: [],
    findingsLoading: false,
    analysisLoading: false,
    totalFindings: 3,
  },
};
