// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import BaseBadge from './BaseBadge.vue';

const meta = {
  title: 'Components/Base/BaseBadge',
  component: BaseBadge,
  argTypes: {
    variant: {
      control: 'select',
      options: ['primary', 'secondary', 'success', 'error', 'warning', 'info', 'light', 'dark'],
      description: 'Badge color variant',
    },
    size: {
      control: 'select',
      options: ['sm', 'md', 'lg'],
      description: 'Badge size',
    },
    pill: {
      control: 'boolean',
      description: 'Rounded badge (pill shape)',
    },
    outlined: {
      control: 'boolean',
      description: 'Outlined badge style',
    },
    label: {
      control: 'text',
      description: 'Badge text',
    },
  },
} as Meta<typeof BaseBadge>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Primary: Story = {
  args: {
    variant: 'primary',
    label: 'Primary',
  },
};

export const Secondary: Story = {
  args: {
    variant: 'secondary',
    label: 'Secondary',
  },
};

export const Success: Story = {
  args: {
    variant: 'success',
    label: 'Success',
  },
};

export const Danger: Story = {
  args: {
    variant: 'error',
    label: 'Danger',
  },
};

export const Warning: Story = {
  args: {
    variant: 'warning',
    label: 'Warning',
  },
};

export const Info: Story = {
  args: {
    variant: 'info',
    label: 'Info',
  },
};

export const Pill: Story = {
  args: {
    variant: 'primary',
    label: 'Pill Badge',
    pill: true,
  },
};

export const Outlined: Story = {
  args: {
    variant: 'primary',
    label: 'Outlined',
    outlined: true,
  },
};

export const Small: Story = {
  args: {
    variant: 'primary',
    label: 'Small',
    size: 'sm',
  },
};

export const Medium: Story = {
  args: {
    variant: 'primary',
    label: 'Medium',
    size: 'md',
  },
};

export const Large: Story = {
  args: {
    variant: 'primary',
    label: 'Large',
    size: 'lg',
  },
};

export const AllVariants: Story = {
  render: () => ({
    components: { BaseBadge },
    template: `
      <div class="flex gap-2 flex-wrap">
        <BaseBadge variant="primary" label="Primary" />
        <BaseBadge variant="secondary" label="Secondary" />
        <BaseBadge variant="success" label="Success" />
        <BaseBadge variant="error" label="Danger" />
        <BaseBadge variant="warning" label="Warning" />
        <BaseBadge variant="info" label="Info" />
        <BaseBadge variant="light" label="Light" />
        <BaseBadge variant="dark" label="Dark" />
      </div>
    `,
  }),
};

export const AllSizes: Story = {
  render: () => ({
    components: { BaseBadge },
    template: `
      <div class="flex gap-2 items-center">
        <BaseBadge variant="primary" label="Small" size="sm" />
        <BaseBadge variant="primary" label="Medium" size="md" />
        <BaseBadge variant="primary" label="Large" size="lg" />
      </div>
    `,
  }),
};

export const Styles: Story = {
  render: () => ({
    components: { BaseBadge },
    template: `
      <div class="space-y-3">
        <div class="flex gap-2">
          <BaseBadge variant="primary" label="Filled" />
          <BaseBadge variant="primary" label="Outlined" outlined />
          <BaseBadge variant="primary" label="Pill" pill />
        </div>
      </div>
    `,
  }),
};
