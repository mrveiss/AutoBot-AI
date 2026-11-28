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
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props.
// The sample findings must still use the real shapes (types/codeIntelligence.ts): the relaxed type
// hid a story built on fields the table never reads, which crashed it (#18694).
type Story = StoryObj<Record<string, unknown>>;

export const Default: Story = {
  args: {
    securityFindings: [
      {
        vulnerability_type: 'sql_injection',
        severity: 'high',
        file_path: 'autobot-backend/api/routes.py',
        line_number: 42,
        code_snippet: 'cursor.execute(f"... {user_input}")',
        message: 'Unsanitized user input used in query',
        remediation: 'Use parameterized queries',
        owasp_category: 'A03:2021-Injection',
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
        vulnerability_type: 'hardcoded_secret',
        severity: 'critical',
        file_path: 'autobot-backend/api/routes.py',
        line_number: 42,
        code_snippet: 'API_KEY = <string literal, elided in this fixture>',
        message: 'API key hardcoded in source',
        remediation: 'Move to environment variable',
        owasp_category: 'A07:2021-Identification and Authentication Failures',
      },
      {
        vulnerability_type: 'weak_hash',
        severity: 'high',
        file_path: 'autobot-backend/auth/handler.py',
        line_number: 15,
        code_snippet: 'hashlib.md5(password)',
        message: 'MD5 used for password hashing',
        remediation: 'Use bcrypt or argon2',
        owasp_category: 'A02:2021-Cryptographic Failures',
      },
    ],
    performanceFindings: [
      {
        issue_type: 'n_plus_one_query',
        severity: 'medium',
        file_path: 'autobot-backend/db/queries.py',
        line_number: 88,
        message: 'Database query in loop',
        recommendation: 'Use batch query',
        estimated_impact: 'One query per row',
      },
    ],
    redisFindings: [],
    findingsLoading: false,
    analysisLoading: false,
    totalFindings: 3,
  },
};
