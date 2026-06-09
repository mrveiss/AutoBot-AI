// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import BaseTable from './BaseTable.vue';

const meta = {
  title: 'Components/Base/BaseTable',
  component: BaseTable,
  argTypes: {
    columns: {
      description: 'Table column definitions',
    },
    data: {
      description: 'Table data rows',
    },
    striped: {
      control: 'boolean',
      description: 'Alternate row colors',
    },
    hover: {
      control: 'boolean',
      description: 'Highlight row on hover',
    },
    bordered: {
      control: 'boolean',
      description: 'Show table borders',
    },
    responsive: {
      control: 'boolean',
      description: 'Make table responsive',
    },
  },
} as Meta<typeof BaseTable>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    columns: [
      { key: 'name', label: 'Name' },
      { key: 'email', label: 'Email' },
      { key: 'role', label: 'Role' },
      { key: 'status', label: 'Status' },
    ],
    data: [
      { id: 1, name: 'John Doe', email: 'john@example.com', role: 'Admin', status: 'Active' },
      { id: 2, name: 'Jane Smith', email: 'jane@example.com', role: 'User', status: 'Active' },
      { id: 3, name: 'Bob Johnson', email: 'bob@example.com', role: 'User', status: 'Inactive' },
    ],
  },
};

export const Striped: Story = {
  args: {
    columns: [
      { key: 'name', label: 'Name' },
      { key: 'department', label: 'Department' },
      { key: 'joined', label: 'Joined' },
    ],
    data: [
      { id: 1, name: 'Alice Brown', department: 'Engineering', joined: '2023-01-15' },
      { id: 2, name: 'Charlie Davis', department: 'Marketing', joined: '2023-03-22' },
      { id: 3, name: 'Diana Evans', department: 'Sales', joined: '2023-05-10' },
      { id: 4, name: 'Edward Frank', department: 'Engineering', joined: '2023-07-18' },
    ],
    striped: true,
  },
};

export const Hoverable: Story = {
  args: {
    columns: [
      { key: 'id', label: 'ID' },
      { key: 'title', label: 'Title' },
      { key: 'progress', label: 'Progress' },
    ],
    data: [
      { id: 1001, title: 'Project Alpha', progress: '75%' },
      { id: 1002, title: 'Project Beta', progress: '50%' },
      { id: 1003, title: 'Project Gamma', progress: '100%' },
    ],
    hover: true,
  },
};

export const Bordered: Story = {
  args: {
    columns: [
      { key: 'product', label: 'Product' },
      { key: 'quantity', label: 'Quantity' },
      { key: 'price', label: 'Price' },
    ],
    data: [
      { id: 1, product: 'Laptop', quantity: 5, price: '$999' },
      { id: 2, product: 'Monitor', quantity: 10, price: '$299' },
      { id: 3, product: 'Keyboard', quantity: 20, price: '$79' },
    ],
    bordered: true,
  },
};

export const StripedAndHoverable: Story = {
  args: {
    columns: [
      { key: 'name', label: 'Name' },
      { key: 'email', label: 'Email' },
      { key: 'status', label: 'Status' },
    ],
    data: [
      { id: 1, name: 'User One', email: 'user1@example.com', status: 'Active' },
      { id: 2, name: 'User Two', email: 'user2@example.com', status: 'Active' },
      { id: 3, name: 'User Three', email: 'user3@example.com', status: 'Pending' },
    ],
    striped: true,
    hover: true,
  },
};
