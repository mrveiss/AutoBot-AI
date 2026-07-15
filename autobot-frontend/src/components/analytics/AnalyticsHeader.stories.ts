// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import AnalyticsHeader from './AnalyticsHeader.vue';

const meta = {
  title: 'Components/Analytics/AnalyticsHeader',
  component: AnalyticsHeader,
  tags: ['autodocs'],
  argTypes: {
    rootPath: { control: 'text' },
    analyzing: { control: 'boolean' },
    currentJobId: { control: 'text' },
    analyzingCodeSmells: { control: 'boolean' },
    exportingReport: { control: 'boolean' },
    clearingCache: { control: 'boolean' },
    sources: { control: 'object' },
    selectedSource: { control: 'object' },
  },
} as Meta<typeof AnalyticsHeader>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

export const Default: Story = {
  args: {
    rootPath: '/opt/autobot',
    analyzing: false,
    currentJobId: null,
    analyzingCodeSmells: false,
    exportingReport: false,
    clearingCache: false,
    sources: [],
    selectedSource: null,
  },
};

export const Analyzing: Story = {
  args: {
    rootPath: '/opt/autobot',
    analyzing: true,
    currentJobId: 'job-abc12345',
    analyzingCodeSmells: false,
    exportingReport: false,
    clearingCache: false,
    sources: [],
    selectedSource: null,
  },
};

export const WithSourceSelected: Story = {
  args: {
    rootPath: '',
    analyzing: false,
    currentJobId: null,
    analyzingCodeSmells: false,
    exportingReport: false,
    clearingCache: false,
    sources: [
      {
        id: 'src-001',
        name: 'AutoBot Backend',
        source_type: 'github',
        repo: 'mrveiss/AutoBot-AI',
        branch: 'Dev_new_gui',
        access: 'private',
        status: 'ready',
      },
    ],
    selectedSource: {
      id: 'src-001',
      name: 'AutoBot Backend',
      source_type: 'github',
      repo: 'mrveiss/AutoBot-AI',
      branch: 'Dev_new_gui',
      access: 'private',
      status: 'ready',
    },
  },
};

export const AnalyzingCodeSmells: Story = {
  args: {
    rootPath: '/opt/autobot',
    analyzing: false,
    currentJobId: null,
    analyzingCodeSmells: true,
    exportingReport: false,
    clearingCache: false,
    sources: [],
    selectedSource: null,
  },
};
