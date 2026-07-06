// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import OverseerPlanMessage from './OverseerPlanMessage.vue';

const meta = {
  title: 'Components/Chat/OverseerPlanMessage',
  component: OverseerPlanMessage,
  tags: ['autodocs'],
  argTypes: {
    plan: {
      control: 'object',
      description: 'OverseerPlan object with analysis and steps',
    },
    steps: {
      control: 'object',
      description: 'Live step status array from the Overseer agent',
    },
  },
} as Meta<typeof OverseerPlanMessage>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

const basePlan = {
  analysis: 'The user wants to check system health and restart the web service if it is down.',
  steps: [
    { step_number: 1, description: 'Check service status', command: 'systemctl status nginx' },
    { step_number: 2, description: 'Restart service if not running', command: 'systemctl restart nginx' },
    { step_number: 3, description: 'Verify service is active', command: 'systemctl is-active nginx' },
  ],
};

export const Pending: Story = {
  args: {
    plan: basePlan,
    steps: [],
  },
};

export const InProgress: Story = {
  args: {
    plan: basePlan,
    steps: [
      { step_number: 1, status: 'completed' },
      { step_number: 2, status: 'running' },
      { step_number: 3, status: 'pending' },
    ],
  },
};

export const Completed: Story = {
  args: {
    plan: basePlan,
    steps: [
      { step_number: 1, status: 'completed' },
      { step_number: 2, status: 'completed' },
      { step_number: 3, status: 'completed' },
    ],
  },
};

export const WithFailure: Story = {
  args: {
    plan: basePlan,
    steps: [
      { step_number: 1, status: 'completed' },
      { step_number: 2, status: 'failed' },
      { step_number: 3, status: 'pending' },
    ],
  },
};
