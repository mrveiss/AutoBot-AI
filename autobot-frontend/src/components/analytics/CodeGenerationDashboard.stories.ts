// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import CodeGenerationDashboard from './CodeGenerationDashboard.vue';

const meta = {
  title: 'Components/Analytics/CodeGenerationDashboard',
  component: CodeGenerationDashboard,
  tags: ['autodocs'],
} as Meta<typeof CodeGenerationDashboard>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

export const Default: Story = {
  args: {},
};

export const GenerateMode: Story = {
  args: {},
};

export const RefactorMode: Story = {
  args: {},
};

export const Loading: Story = {
  args: {},
};
