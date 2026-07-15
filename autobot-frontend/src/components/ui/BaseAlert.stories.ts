// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import BaseAlert from './BaseAlert.vue';

const meta = {
  title: 'Components/UI/BaseAlert',
  component: BaseAlert,
  argTypes: {
    variant: {
      control: 'select',
      options: ['success', 'info', 'warning', 'error', 'critical'],
      description: 'Alert variant',
    },
    size: {
      control: 'select',
      options: ['default', 'compact'],
      description: 'Size variant — compact hides the title and uses reduced padding (for inline field errors)',
    },
    title: {
      control: 'text',
      description: 'Alert title (hidden in compact size)',
    },
    message: {
      control: 'text',
      description: 'Alert message',
    },
    dismissible: {
      control: 'boolean',
      description: 'Show dismiss button',
    },
    icon: {
      control: 'boolean',
      description: 'Show icon',
    },
  },
} as Meta<typeof BaseAlert>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

export const Success: Story = {
  args: {
    variant: 'success',
    title: 'Success',
    message: 'Operation completed successfully',
  },
};

export const Error: Story = {
  args: {
    variant: 'error',
    title: 'Error',
    message: 'An error occurred while processing your request',
  },
};

export const Warning: Story = {
  args: {
    variant: 'warning',
    title: 'Warning',
    message: 'Please review this information before proceeding',
  },
};

export const Info: Story = {
  args: {
    variant: 'info',
    title: 'Information',
    message: 'Here is some important information for you',
  },
};

export const Closable: Story = {
  args: {
    variant: 'info',
    title: 'Closable Alert',
    message: 'This alert can be dismissed by clicking the close button',
    dismissible: true,
  },
};

export const NoIcon: Story = {
  args: {
    variant: 'success',
    title: 'Success',
    message: 'Operation completed without displaying an icon',
    icon: false,
  },
};

/** Compact size — intended for inline field-level errors below form inputs */
export const CompactError: Story = {
  args: {
    variant: 'error',
    size: 'compact',
    message: 'This field is required',
  },
};

export const CompactWarning: Story = {
  args: {
    variant: 'warning',
    size: 'compact',
    message: 'Value exceeds recommended limit',
  },
};

/** All compact variants side by side */
export const CompactAllVariants: Story = {
  render: () => ({
    components: { BaseAlert },
    template: `
      <div class="space-y-2">
        <BaseAlert variant="error" size="compact" message="Email address is required" />
        <BaseAlert variant="warning" size="compact" message="Password must be at least 8 characters" />
        <BaseAlert variant="info" size="compact" message="Username is already taken" />
        <BaseAlert variant="success" size="compact" message="Field validated successfully" />
      </div>
    `,
  }),
};

export const AllTypes: Story = {
  render: () => ({
    components: { BaseAlert },
    template: `
      <div class="space-y-4">
        <BaseAlert variant="success" title="Success" message="This is a success alert message" dismissible />
        <BaseAlert variant="error" title="Error" message="This is an error alert message" dismissible />
        <BaseAlert variant="warning" title="Warning" message="This is a warning alert message" dismissible />
        <BaseAlert variant="info" title="Information" message="This is an info alert message" dismissible />
      </div>
    `,
  }),
};
