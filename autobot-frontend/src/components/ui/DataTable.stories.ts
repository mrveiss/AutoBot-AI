// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import DataTable from './DataTable.vue';

const meta = {
  title: 'Components/UI/DataTable',
  component: DataTable,
  argTypes: {
    columns: {
      control: 'object',
      description: 'Table column definitions (key, label, sortable?, format?)',
    },
    data: {
      control: 'object',
      description: 'Array of row data objects',
    },
    showHeader: {
      control: 'boolean',
      description: 'Show table header bar with title and actions',
    },
    title: {
      control: 'text',
      description: 'Title shown in the header bar',
    },
    pagination: {
      control: 'boolean',
      description: 'Enable pagination',
    },
    itemsPerPage: {
      control: 'number',
      description: 'Items per page when pagination is enabled',
    },
    loading: {
      control: 'boolean',
      description: 'Show loading spinner instead of rows',
    },
    emptyIcon: {
      control: 'text',
      description: 'IconName from registry for empty state',
    },
    emptyTitle: {
      control: 'text',
      description: 'Title for empty state',
    },
    emptyMessage: {
      control: 'text',
      description: 'Message for empty state',
    },
  },
} as Meta<typeof DataTable>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

const sampleColumns = [
  { key: 'name', label: 'Name', sortable: true },
  { key: 'role', label: 'Role', sortable: true },
  { key: 'status', label: 'Status' },
];

const sampleData = [
  { name: 'Alice Walker', role: 'Engineer', status: 'Active' },
  { name: 'Bob Chen', role: 'Designer', status: 'Active' },
  { name: 'Carol Diaz', role: 'PM', status: 'Inactive' },
  { name: 'David Edwards', role: 'Engineer', status: 'Active' },
];

export const Default: Story = {
  args: {
    columns: sampleColumns,
    data: sampleData,
    title: 'Team Members',
  },
};

export const WithoutHeader: Story = {
  args: {
    columns: sampleColumns,
    data: sampleData,
    showHeader: false,
  },
};

export const Loading: Story = {
  args: {
    columns: sampleColumns,
    data: [],
    title: 'Team Members',
    loading: true,
  },
};

export const Empty: Story = {
  args: {
    columns: sampleColumns,
    data: [],
    title: 'Team Members',
    emptyTitle: 'No members yet',
    emptyMessage: 'Invite teammates to get started.',
    emptyIcon: 'users',
  },
};

export const WithPagination: Story = {
  args: {
    columns: sampleColumns,
    data: Array.from({ length: 25 }, (_, i) => ({
      name: `User ${i + 1}`,
      role: i % 2 === 0 ? 'Engineer' : 'Designer',
      status: i % 3 === 0 ? 'Inactive' : 'Active',
    })),
    title: 'All Users',
    pagination: true,
    itemsPerPage: 5,
  },
};

export const SortableColumns: Story = {
  args: {
    columns: [
      { key: 'name', label: 'Name', sortable: true },
      { key: 'score', label: 'Score', sortable: true },
      { key: 'team', label: 'Team', sortable: true },
    ],
    data: [
      { name: 'Alpha', score: 92, team: 'Red' },
      { name: 'Bravo', score: 87, team: 'Blue' },
      { name: 'Charlie', score: 95, team: 'Red' },
      { name: 'Delta', score: 71, team: 'Green' },
    ],
    title: 'Leaderboard',
  },
};

export const WithCustomCells: Story = {
  render: () => ({
    components: { DataTable },
    setup() {
      return {
        columns: [
          { key: 'name', label: 'Service', sortable: true },
          { key: 'status', label: 'Status' },
          { key: 'uptime', label: 'Uptime', sortable: true },
        ],
        data: [
          { name: 'API', status: 'healthy', uptime: '99.99%' },
          { name: 'Database', status: 'degraded', uptime: '98.50%' },
          { name: 'Worker', status: 'down', uptime: '85.20%' },
        ],
      };
    },
    template: `
      <DataTable :columns="columns" :data="data" title="Services">
        <template #cell-status="{ value }">
          <span
            :class="{
              'text-green-600': value === 'healthy',
              'text-yellow-600': value === 'degraded',
              'text-red-600': value === 'down',
            }"
            class="font-semibold capitalize"
          >
            {{ value }}
          </span>
        </template>
        <template #actions="{ row }">
          <button class="text-blue-600 hover:underline">Edit {{ row.name }}</button>
        </template>
      </DataTable>
    `,
  }),
};
