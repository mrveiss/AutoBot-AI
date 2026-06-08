// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import ActivityFeed from './ActivityFeed.vue';

const meta = {
  title: 'Components/Collaboration/ActivityFeed',
  component: ActivityFeed,
  tags: ['autodocs'],
  argTypes: {},
} as Meta<typeof ActivityFeed>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<any>;

export const Default: Story = {
  render: () => ({
    components: { ActivityFeed },
    template: `<ActivityFeed />`,
  }),
};

export const Connected: Story = {
  name: 'Connected with activity',
  render: () => ({
    components: { ActivityFeed },
    template: `
      <div style="height: 400px; width: 320px;">
        <ActivityFeed />
      </div>
    `,
  }),
};

export const Empty: Story = {
  name: 'Empty state (no activity)',
  render: () => ({
    components: { ActivityFeed },
    template: `
      <div style="height: 300px; width: 320px;">
        <ActivityFeed />
      </div>
    `,
  }),
};

export const Compact: Story = {
  name: 'Compact container',
  render: () => ({
    components: { ActivityFeed },
    template: `
      <div style="height: 200px; width: 260px;">
        <ActivityFeed />
      </div>
    `,
  }),
};

export const Wide: Story = {
  name: 'Wide layout',
  render: () => ({
    components: { ActivityFeed },
    template: `
      <div style="height: 480px; width: 480px;">
        <ActivityFeed />
      </div>
    `,
  }),
};
