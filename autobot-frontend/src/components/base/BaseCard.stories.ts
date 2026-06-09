// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import BaseCard from './BaseCard.vue';

const meta = {
  title: 'Components/Base/BaseCard',
  component: BaseCard,
  argTypes: {
    variant: {
      control: 'select',
      options: ['default', 'elevated', 'outline', 'filled'],
      description: 'Card style variant',
    },
    padding: {
      control: 'select',
      options: ['none', 'sm', 'md', 'lg'],
      description: 'Internal padding size',
    },
    hoverable: {
      control: 'boolean',
      description: 'Enable hover effects',
    },
  },
} as Meta<typeof BaseCard>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    variant: 'default',
    padding: 'md',
  },
  render: (args: any) => ({
    components: { BaseCard },
    setup() {
      return { args };
    },
    template: `
      <BaseCard v-bind="args">
        <h3 class="text-lg font-bold mb-2">Card Title</h3>
        <p class="text-gray-600">This is the card content. You can add any content here.</p>
      </BaseCard>
    `,
  }),
};

export const Elevated: Story = {
  args: {
    variant: 'elevated',
    padding: 'md',
  },
  render: (args: any) => ({
    components: { BaseCard },
    setup() {
      return { args };
    },
    template: `
      <BaseCard v-bind="args">
        <h3 class="text-lg font-bold mb-2">Elevated Card</h3>
        <p class="text-gray-600">This card has an elevated shadow style.</p>
      </BaseCard>
    `,
  }),
};

export const Outline: Story = {
  args: {
    variant: 'outline',
    padding: 'md',
  },
  render: (args: any) => ({
    components: { BaseCard },
    setup() {
      return { args };
    },
    template: `
      <BaseCard v-bind="args">
        <h3 class="text-lg font-bold mb-2">Outline Card</h3>
        <p class="text-gray-600">This card uses an outline style.</p>
      </BaseCard>
    `,
  }),
};

export const Hoverable: Story = {
  args: {
    variant: 'default',
    padding: 'md',
    hoverable: true,
  },
  render: (args: any) => ({
    components: { BaseCard },
    setup() {
      return { args };
    },
    template: `
      <BaseCard v-bind="args">
        <h3 class="text-lg font-bold mb-2">Hoverable Card</h3>
        <p class="text-gray-600">Hover over this card to see the effect.</p>
      </BaseCard>
    `,
  }),
};

export const NoPadding: Story = {
  args: {
    variant: 'default',
    padding: 'none',
  },
  render: (args: any) => ({
    components: { BaseCard },
    setup() {
      return { args };
    },
    template: `
      <BaseCard v-bind="args" class="overflow-hidden">
        <div class="bg-blue-500 h-40 flex items-center justify-center text-white font-bold">
          Full Width Image Area
        </div>
        <div class="p-4">
          <h3 class="text-lg font-bold">With Custom Padding</h3>
        </div>
      </BaseCard>
    `,
  }),
};

export const WithSlots: Story = {
  render: () => ({
    components: { BaseCard },
    template: `
      <BaseCard>
        <template #header>
          <div class="text-lg font-bold">Card Header</div>
        </template>
        <div>Card content goes here</div>
        <template #footer>
          <div class="text-sm text-gray-500">Card Footer</div>
        </template>
      </BaseCard>
    `,
  }),
};
