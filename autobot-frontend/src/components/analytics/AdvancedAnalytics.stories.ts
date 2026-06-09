// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import AdvancedAnalytics from './AdvancedAnalytics.vue';

const meta = {
  title: 'Components/Analytics/AdvancedAnalytics',
  component: AdvancedAnalytics,
  tags: ['autodocs'],
} as Meta<typeof AdvancedAnalytics>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {},
};

export const Loading: Story = {
  render: () => ({
    template: '<AdvancedAnalytics />',
    components: { AdvancedAnalytics },
  }),
};

export const CostTab: Story = {
  args: {},
};

export const AgentsTab: Story = {
  args: {},
};

export const ExportTab: Story = {
  args: {},
};
