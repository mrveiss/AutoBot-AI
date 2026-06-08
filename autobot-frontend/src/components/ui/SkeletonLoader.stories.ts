// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import SkeletonLoader from './SkeletonLoader.vue';

const meta = {
  title: 'Components/UI/SkeletonLoader',
  component: SkeletonLoader,
  argTypes: {
    variant: {
      control: 'select',
      options: ['chat-message', 'knowledge-card', 'file-list', 'stats-cards', 'custom'],
      description: 'Predefined layout',
    },
    count: {
      control: { type: 'number', min: 1, max: 10 },
      description: 'Number of items in list/grid variants',
    },
    animated: {
      control: 'boolean',
      description: 'Apply shimmer animation',
    },
    theme: {
      control: 'select',
      options: ['light', 'dark'],
      description: 'Theme variant',
    },
    rounded: {
      control: 'boolean',
      description: 'Round skeleton element corners',
    },
    lines: {
      control: { type: 'number', min: 1, max: 10 },
      description: 'Number of lines for the custom variant default',
    },
    width: {
      control: 'select',
      options: ['full', '3/4', '1/2', '1/4'],
      description: 'Custom variant default line width',
    },
  },
} as Meta<typeof SkeletonLoader>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    variant: 'custom',
    count: 3,
  },
};

export const ChatMessage: Story = {
  args: {
    variant: 'chat-message',
  },
};

export const KnowledgeCard: Story = {
  args: {
    variant: 'knowledge-card',
  },
};

export const FileList: Story = {
  args: {
    variant: 'file-list',
    count: 4,
  },
};

export const StatsCards: Story = {
  args: {
    variant: 'stats-cards',
    count: 4,
  },
};

export const DarkTheme: Story = {
  args: {
    variant: 'knowledge-card',
    theme: 'dark',
  },
  decorators: [
    () => ({
      template: '<div class="bg-gray-900 p-6 rounded"><story /></div>',
    }),
  ],
};

export const NoAnimation: Story = {
  args: {
    variant: 'file-list',
    count: 3,
    animated: false,
  },
};

export const AllVariants: Story = {
  render: () => ({
    components: { SkeletonLoader },
    template: `
      <div class="flex flex-col gap-6 max-w-3xl">
        <div>
          <h4 class="text-sm font-semibold mb-2">chat-message</h4>
          <SkeletonLoader variant="chat-message" />
        </div>
        <div>
          <h4 class="text-sm font-semibold mb-2">knowledge-card</h4>
          <SkeletonLoader variant="knowledge-card" />
        </div>
        <div>
          <h4 class="text-sm font-semibold mb-2">file-list</h4>
          <SkeletonLoader variant="file-list" :count="3" />
        </div>
        <div>
          <h4 class="text-sm font-semibold mb-2">stats-cards</h4>
          <SkeletonLoader variant="stats-cards" :count="3" />
        </div>
      </div>
    `,
  }),
};
