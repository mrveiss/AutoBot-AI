// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import ImportTreeChart from './ImportTreeChart.vue';

const meta = {
  title: 'Components/Charts/ImportTreeChart',
  component: ImportTreeChart,
  tags: ['autodocs'],
  argTypes: {
    title: {
      control: 'text',
      description: 'Chart title',
    },
    subtitle: {
      control: 'text',
      description: 'Chart subtitle',
    },
    height: {
      control: 'number',
      description: 'Container height in pixels',
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
} as Meta<typeof ImportTreeChart>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<any>;

const sampleData = [
  {
    path: 'src/app/main.py',
    imports: [
      { module: 'fastapi', is_external: true },
      { module: 'src.db.client', file: 'src/db/client.py', is_external: false },
      { module: 'src.api.routes', file: 'src/api/routes.py', is_external: false },
    ],
    imported_by: [],
  },
  {
    path: 'src/db/client.py',
    imports: [
      { module: 'sqlalchemy', is_external: true },
      { module: 'redis', is_external: true },
    ],
    imported_by: [
      { file: 'src/app/main.py', module: 'src.db.client' },
      { file: 'src/api/routes.py', module: 'src.db.client' },
    ],
  },
  {
    path: 'src/api/routes.py',
    imports: [
      { module: 'fastapi', is_external: true },
      { module: 'src.db.client', file: 'src/db/client.py', is_external: false },
    ],
    imported_by: [
      { file: 'src/app/main.py', module: 'src.api.routes' },
    ],
  },
  {
    path: 'src/utils/helpers.py',
    imports: [
      { module: 'typing', is_external: true },
    ],
    imported_by: [],
  },
];

export const Default: Story = {
  args: {
    data: sampleData,
    height: 600,
  },
};

export const WithCustomTitle: Story = {
  args: {
    data: sampleData,
    title: 'Module Import Relationships',
    subtitle: 'Visualizing dependencies between source files',
    height: 600,
  },
};

export const SmallProject: Story = {
  args: {
    data: sampleData.slice(0, 2),
    title: 'Simple Import Tree',
    height: 500,
  },
};

export const LoadingState: Story = {
  args: {
    data: [],
    loading: true,
    height: 600,
  },
};

export const ErrorState: Story = {
  args: {
    data: [],
    error: 'Failed to load import tree data.',
    height: 600,
  },
};
