// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import MarketplaceSourcesModal from './MarketplaceSourcesModal.vue';

const meta = {
  title: 'Components/Plugins/MarketplaceSourcesModal',
  component: MarketplaceSourcesModal,
  argTypes: {
    open: {
      control: 'boolean',
      description: 'Controls whether the modal is visible',
    },
  },
} as Meta<typeof MarketplaceSourcesModal>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

export const Open: Story = {
  args: {
    open: true,
  },
  render: (args: Record<string, unknown>) => ({
    components: { MarketplaceSourcesModal },
    setup() {
      return { args };
    },
    template: `
      <div style="position: relative; width: 100%; height: 600px;">
        <p class="mb-4 text-sm text-gray-500">
          MarketplaceSourcesModal manages the list of marketplace plugin sources.
          It allows adding new sources (name + URL) and removing custom ones.
          Built-in sources are read-only and display a badge.
        </p>
        <MarketplaceSourcesModal :open="args.open" @close="args.open = false" @updated="() => {}" />
      </div>
    `,
  }),
};

export const Closed: Story = {
  args: {
    open: false,
  },
  render: (args: Record<string, unknown>) => ({
    components: { MarketplaceSourcesModal },
    setup() {
      return { args };
    },
    template: `
      <div>
        <p class="mb-4 text-sm text-gray-500">
          When <code>open</code> is false the modal is hidden — nothing is rendered to the DOM.
        </p>
        <MarketplaceSourcesModal :open="args.open" @close="args.open = false" @updated="() => {}" />
        <p class="mt-4 text-sm text-gray-400">Modal is hidden in this state.</p>
      </div>
    `,
  }),
};
