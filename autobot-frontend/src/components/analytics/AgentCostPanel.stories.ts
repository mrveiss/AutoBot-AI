// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import AgentCostPanel from './AgentCostPanel.vue';

const meta = {
  title: 'Components/Analytics/AgentCostPanel',
  component: AgentCostPanel,
  tags: ['autodocs'],
} as Meta<typeof AgentCostPanel>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {},
};

export const WithData: Story = {
  args: {},
  render: () => ({
    template: '<AgentCostPanel />',
    components: { AgentCostPanel },
  }),
};

export const Empty: Story = {
  args: {},
};

export const WithBudgetExceeded: Story = {
  args: {},
};
