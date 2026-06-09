// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import LoadingSpinner from './LoadingSpinner.vue';

const meta = {
  title: 'Components/UI/LoadingSpinner',
  component: LoadingSpinner,
  argTypes: {
    size: {
      control: 'select',
      options: ['sm', 'md', 'lg', 'xl'],
      description: 'Spinner size',
    },
    color: {
      control: 'text',
      description: 'Spinner color (CSS color value)',
    },
    text: {
      control: 'text',
      description: 'Loading text',
    },
  },
} as Meta<typeof LoadingSpinner>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    size: 'md',
  },
};

export const Small: Story = {
  args: {
    size: 'sm',
  },
};

export const Medium: Story = {
  args: {
    size: 'md',
  },
};

export const Large: Story = {
  args: {
    size: 'lg',
  },
};

export const ExtraLarge: Story = {
  args: {
    size: 'xl',
  },
};

export const WithText: Story = {
  args: {
    size: 'md',
    text: 'Loading...',
  },
};

export const AllSizes: Story = {
  render: () => ({
    components: { LoadingSpinner },
    template: `
      <div class="flex gap-8 items-center">
        <div class="flex flex-col items-center gap-2">
          <LoadingSpinner size="sm" />
          <span class="text-sm">Small</span>
        </div>
        <div class="flex flex-col items-center gap-2">
          <LoadingSpinner size="md" />
          <span class="text-sm">Medium</span>
        </div>
        <div class="flex flex-col items-center gap-2">
          <LoadingSpinner size="lg" />
          <span class="text-sm">Large</span>
        </div>
        <div class="flex flex-col items-center gap-2">
          <LoadingSpinner size="xl" />
          <span class="text-sm">Extra Large</span>
        </div>
      </div>
    `,
  }),
};
