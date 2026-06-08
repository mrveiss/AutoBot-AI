// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import CodeQualityDashboard from './CodeQualityDashboard.vue';

const meta = {
  title: 'Components/Analytics/CodeQualityDashboard',
  component: CodeQualityDashboard,
  tags: ['autodocs'],
} as Meta<typeof CodeQualityDashboard>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {},
};

export const Loading: Story = {
  args: {},
};

export const Connected: Story = {
  args: {},
  render: () => ({
    template: '<CodeQualityDashboard />',
    components: { CodeQualityDashboard },
  }),
};

export const NoData: Story = {
  args: {},
};
