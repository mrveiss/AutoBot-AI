// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import TouchFriendlyButton from './TouchFriendlyButton.vue';

const meta = {
  title: 'Components/UI/TouchFriendlyButton',
  component: TouchFriendlyButton,
  argTypes: {
    variant: {
      control: 'select',
      options: ['primary', 'secondary', 'outline-solid', 'ghost', 'error'],
      description: 'Button style variant',
    },
    size: {
      control: 'select',
      options: ['xs', 'sm', 'md', 'lg', 'xl'],
      description: 'Button size',
    },
    loading: {
      control: 'boolean',
      description: 'Show loading spinner overlay',
    },
    disabled: {
      control: 'boolean',
      description: 'Disable the button',
    },
    loadingVariant: {
      control: 'select',
      options: ['circle', 'dots', 'pulse'],
      description: 'Loading spinner variant',
    },
    loadingSize: {
      control: 'select',
      options: ['xs', 'sm', 'md'],
      description: 'Loading spinner size',
    },
    touchFeedback: {
      control: 'boolean',
      description: 'Enable touch ripple effect',
    },
    hapticFeedback: {
      control: 'boolean',
      description: 'Trigger device vibration on touch (when supported)',
    },
  },
} as Meta<typeof TouchFriendlyButton>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Primary: Story = {
  render: () => ({
    components: { TouchFriendlyButton },
    template: '<TouchFriendlyButton variant="primary">Primary</TouchFriendlyButton>',
  }),
};

export const Secondary: Story = {
  render: () => ({
    components: { TouchFriendlyButton },
    template: '<TouchFriendlyButton variant="secondary">Secondary</TouchFriendlyButton>',
  }),
};

export const Ghost: Story = {
  render: () => ({
    components: { TouchFriendlyButton },
    template: '<TouchFriendlyButton variant="ghost">Ghost</TouchFriendlyButton>',
  }),
};

export const Danger: Story = {
  render: () => ({
    components: { TouchFriendlyButton },
    template: '<TouchFriendlyButton variant="error">Delete</TouchFriendlyButton>',
  }),
};

export const Loading: Story = {
  render: () => ({
    components: { TouchFriendlyButton },
    template: '<TouchFriendlyButton variant="primary" :loading="true">Submitting</TouchFriendlyButton>',
  }),
};

export const Disabled: Story = {
  render: () => ({
    components: { TouchFriendlyButton },
    template: '<TouchFriendlyButton variant="primary" :disabled="true">Disabled</TouchFriendlyButton>',
  }),
};

export const AllSizes: Story = {
  render: () => ({
    components: { TouchFriendlyButton },
    template: `
      <div class="flex items-center flex-wrap gap-2">
        <TouchFriendlyButton size="xs">XS</TouchFriendlyButton>
        <TouchFriendlyButton size="sm">SM</TouchFriendlyButton>
        <TouchFriendlyButton size="md">MD</TouchFriendlyButton>
        <TouchFriendlyButton size="lg">LG</TouchFriendlyButton>
        <TouchFriendlyButton size="xl">XL</TouchFriendlyButton>
      </div>
    `,
  }),
};

export const AllVariants: Story = {
  render: () => ({
    components: { TouchFriendlyButton },
    template: `
      <div class="flex flex-wrap gap-2">
        <TouchFriendlyButton variant="primary">Primary</TouchFriendlyButton>
        <TouchFriendlyButton variant="secondary">Secondary</TouchFriendlyButton>
        <TouchFriendlyButton variant="outline-solid">Outline</TouchFriendlyButton>
        <TouchFriendlyButton variant="ghost">Ghost</TouchFriendlyButton>
        <TouchFriendlyButton variant="error">Danger</TouchFriendlyButton>
      </div>
    `,
  }),
};
