// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import CodeEvolutionTimeline from './CodeEvolutionTimeline.vue';

const meta = {
  title: 'Components/Analytics/CodeEvolutionTimeline',
  component: CodeEvolutionTimeline,
  tags: ['autodocs'],
} as Meta<typeof CodeEvolutionTimeline>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {},
};

export const Loading: Story = {
  args: {},
  render: () => ({
    template: '<CodeEvolutionTimeline />',
    components: { CodeEvolutionTimeline },
  }),
};

export const DailyGranularity: Story = {
  args: {},
};

export const WeeklyGranularity: Story = {
  args: {},
};
