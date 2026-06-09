// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import ModuleImportsChart from './ModuleImportsChart.vue';

const meta = {
  title: 'Components/Charts/ModuleImportsChart',
  component: ModuleImportsChart,
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
    maxModules: {
      control: 'number',
      description: 'Maximum number of modules to display',
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
} as Meta<typeof ModuleImportsChart>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<any>;

const sampleData = [
  { path: 'src/services/auth.py', name: 'auth', package: 'services', import_count: 42, functions: 12, classes: 3 },
  { path: 'src/db/client.py', name: 'client', package: 'db', import_count: 38, functions: 8, classes: 2 },
  { path: 'src/utils/helpers.py', name: 'helpers', package: 'utils', import_count: 31, functions: 20, classes: 0 },
  { path: 'src/api/middleware.py', name: 'middleware', package: 'api', import_count: 27, functions: 6, classes: 4 },
  { path: 'src/models/user.py', name: 'user', package: 'models', import_count: 24, functions: 5, classes: 1 },
  { path: 'src/config/settings.py', name: 'settings', package: 'config', import_count: 19, functions: 2, classes: 1 },
  { path: 'src/tasks/worker.py', name: 'worker', package: 'tasks', import_count: 15, functions: 9, classes: 2 },
  { path: 'src/cache/redis_cache.py', name: 'redis_cache', package: 'cache', import_count: 12, functions: 7, classes: 1 },
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
    title: 'Most Imported Modules',
    subtitle: 'Top modules by import count across the codebase',
    height: 400,
  },
};

export const LimitedModules: Story = {
  args: {
    data: sampleData,
    maxModules: 5,
    title: 'Top 5 Modules',
    height: 300,
  },
};

export const LoadingState: Story = {
  args: {
    data: [],
    loading: true,
    height: 400,
  },
};

export const ErrorState: Story = {
  args: {
    data: [],
    error: 'Failed to load module import data.',
    height: 400,
  },
};
