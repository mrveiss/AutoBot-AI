// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import LogPatternDashboard from './LogPatternDashboard.vue';

const meta = {
  title: 'Components/Analytics/LogPatternDashboard',
  component: LogPatternDashboard,
  tags: ['autodocs'],
} as Meta<typeof LogPatternDashboard>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {},
};

export const Analyzing: Story = {
  args: {},
};

export const WithPatterns: Story = {
  args: {},
  render: () => ({
    template: '<LogPatternDashboard />',
    components: { LogPatternDashboard },
  }),
};

export const Last24Hours: Story = {
  args: {},
};
