// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import StatusBadge from './StatusBadge.vue';

const meta = {
  title: 'Components/UI/StatusBadge',
  component: StatusBadge,
  argTypes: {
    variant: {
      control: 'select',
      options: ['success', 'error', 'warning', 'info', 'secondary', 'primary'],
      description: 'Color variant',
    },
    size: {
      control: 'select',
      options: ['sm', 'md', 'lg'],
      description: 'Badge size',
    },
    icon: {
      control: 'select',
      options: [undefined, 'check-circle', 'exclamation-triangle', 'exclamation-circle', 'info-circle', 'clock', 'circle'],
      description: 'Optional leading icon',
    },
  },
} as Meta<typeof StatusBadge>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Success: Story = {
  render: () => ({
    components: { StatusBadge },
    template: '<StatusBadge variant="success" icon="check-circle">Active</StatusBadge>',
  }),
};

export const Danger: Story = {
  render: () => ({
    components: { StatusBadge },
    template: '<StatusBadge variant="error" icon="exclamation-circle">Failed</StatusBadge>',
  }),
};

export const Warning: Story = {
  render: () => ({
    components: { StatusBadge },
    template: '<StatusBadge variant="warning" icon="exclamation-triangle">Pending</StatusBadge>',
  }),
};

export const Info: Story = {
  render: () => ({
    components: { StatusBadge },
    template: '<StatusBadge variant="info" icon="info-circle">Running</StatusBadge>',
  }),
};

export const Primary: Story = {
  render: () => ({
    components: { StatusBadge },
    template: '<StatusBadge variant="primary">New</StatusBadge>',
  }),
};

export const Secondary: Story = {
  render: () => ({
    components: { StatusBadge },
    template: '<StatusBadge variant="secondary">Draft</StatusBadge>',
  }),
};

export const Small: Story = {
  render: () => ({
    components: { StatusBadge },
    template: '<StatusBadge variant="success" size="sm" icon="check-circle">OK</StatusBadge>',
  }),
};

export const Large: Story = {
  render: () => ({
    components: { StatusBadge },
    template: '<StatusBadge variant="error" size="lg" icon="exclamation-circle">Critical</StatusBadge>',
  }),
};

export const AllVariants: Story = {
  render: () => ({
    components: { StatusBadge },
    template: `
      <div class="flex flex-wrap gap-2">
        <StatusBadge variant="success" icon="check-circle">Success</StatusBadge>
        <StatusBadge variant="error" icon="exclamation-circle">Danger</StatusBadge>
        <StatusBadge variant="warning" icon="exclamation-triangle">Warning</StatusBadge>
        <StatusBadge variant="info" icon="info-circle">Info</StatusBadge>
        <StatusBadge variant="primary">Primary</StatusBadge>
        <StatusBadge variant="secondary">Secondary</StatusBadge>
      </div>
    `,
  }),
};

export const AllSizes: Story = {
  render: () => ({
    components: { StatusBadge },
    template: `
      <div class="flex items-center gap-2">
        <StatusBadge variant="success" size="sm" icon="check-circle">Small</StatusBadge>
        <StatusBadge variant="success" size="md" icon="check-circle">Medium</StatusBadge>
        <StatusBadge variant="success" size="lg" icon="check-circle">Large</StatusBadge>
      </div>
    `,
  }),
};
