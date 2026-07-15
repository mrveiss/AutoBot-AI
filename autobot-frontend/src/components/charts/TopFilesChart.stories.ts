// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import TopFilesChart from './TopFilesChart.vue';

const meta = {
  title: 'Components/Charts/TopFilesChart',
  component: TopFilesChart,
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
    maxFiles: {
      control: 'number',
      description: 'Maximum number of files to display',
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
} as Meta<typeof TopFilesChart>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<Record<string, unknown>>;

const sampleData = [
  { file: 'src/services/auth_service.py', count: 47 },
  { file: 'src/api/v1/endpoints/users.py', count: 38 },
  { file: 'src/db/repositories/user_repo.py', count: 31 },
  { file: 'src/utils/validation.py', count: 28 },
  { file: 'src/models/domain/user.py', count: 24 },
  { file: 'src/api/middleware/auth.py', count: 19 },
  { file: 'src/tasks/email_worker.py', count: 16 },
  { file: 'src/config/settings.py', count: 13 },
  { file: 'src/cache/session_cache.py', count: 11 },
  { file: 'src/utils/crypto.py', count: 9 },
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
    title: 'Files with Most Issues',
    subtitle: 'Top files ranked by problem count',
    height: 400,
  },
};

export const LimitedFiles: Story = {
  args: {
    data: sampleData,
    maxFiles: 5,
    title: 'Top 5 Problematic Files',
    height: 300,
  },
};

export const NameValueFormat: Story = {
  args: {
    data: [
      { name: 'main.py', value: 55 },
      { name: 'utils.py', value: 42 },
      { name: 'models.py', value: 30 },
    ],
    title: 'Files (name/value format)',
    height: 250,
  },
};

export const LoadingState: Story = {
  args: {
    data: [],
    loading: true,
    height: 400,
  },
};
