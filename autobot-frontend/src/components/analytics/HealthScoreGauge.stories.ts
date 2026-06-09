// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import HealthScoreGauge from './HealthScoreGauge.vue';

const meta = {
  title: 'Components/Analytics/HealthScoreGauge',
  component: HealthScoreGauge,
  tags: ['autodocs'],
  argTypes: {
    score: { control: { type: 'range', min: 0, max: 100 } },
    grade: { control: 'text' },
    label: { control: 'text' },
    statusMessage: { control: 'text' },
  },
} as Meta<typeof HealthScoreGauge>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    score: 85,
    grade: 'B',
    label: 'Code Health',
    statusMessage: 'Good overall quality',
  },
};

export const Excellent: Story = {
  args: {
    score: 95,
    grade: 'A',
    label: 'Code Health',
    statusMessage: 'Excellent quality',
  },
};

export const Poor: Story = {
  args: {
    score: 35,
    grade: 'F',
    label: 'Code Health',
    statusMessage: 'Needs significant improvement',
  },
};

export const Average: Story = {
  args: {
    score: 65,
    grade: 'C',
    label: 'Code Health',
  },
};

export const NoMessage: Story = {
  args: {
    score: 78,
    grade: 'B',
    label: 'Overall Score',
  },
};
