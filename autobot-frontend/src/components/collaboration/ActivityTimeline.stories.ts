// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import ActivityTimeline from './ActivityTimeline.vue';

const meta = {
  title: 'Components/Collaboration/ActivityTimeline',
  component: ActivityTimeline,
  tags: ['autodocs'],
  argTypes: {},
} as Meta<typeof ActivityTimeline>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<Record<string, unknown>>;

export const Default: Story = {
  render: () => ({
    components: { ActivityTimeline },
    template: `<ActivityTimeline />`,
  }),
};

export const FullHeight: Story = {
  name: 'Full height container',
  render: () => ({
    components: { ActivityTimeline },
    template: `
      <div style="height: 600px; width: 400px;">
        <ActivityTimeline />
      </div>
    `,
  }),
};

export const NoSession: Story = {
  name: 'No session selected state',
  render: () => ({
    components: { ActivityTimeline },
    template: `
      <div style="height: 400px; width: 360px;">
        <ActivityTimeline />
      </div>
    `,
  }),
};

export const NarrowLayout: Story = {
  name: 'Narrow layout',
  render: () => ({
    components: { ActivityTimeline },
    template: `
      <div style="height: 500px; width: 280px;">
        <ActivityTimeline />
      </div>
    `,
  }),
};

export const WideLayout: Story = {
  name: 'Wide layout',
  render: () => ({
    components: { ActivityTimeline },
    template: `
      <div style="height: 500px; width: 600px;">
        <ActivityTimeline />
      </div>
    `,
  }),
};
