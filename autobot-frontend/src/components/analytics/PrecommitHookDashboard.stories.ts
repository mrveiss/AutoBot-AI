// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import PrecommitHookDashboard from './PrecommitHookDashboard.vue';

const meta = {
  title: 'Components/Analytics/PrecommitHookDashboard',
  component: PrecommitHookDashboard,
  tags: ['autodocs'],
} as Meta<typeof PrecommitHookDashboard>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {},
};

export const HooksInstalled: Story = {
  args: {},
  render: () => ({
    template: '<PrecommitHookDashboard />',
    components: { PrecommitHookDashboard },
  }),
};

export const HooksNotInstalled: Story = {
  args: {},
};

export const CheckFailed: Story = {
  args: {},
};
