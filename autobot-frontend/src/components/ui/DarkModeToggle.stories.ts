// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import DarkModeToggle from './DarkModeToggle.vue';

const meta = {
  title: 'Components/UI/DarkModeToggle',
  component: DarkModeToggle,
  argTypes: {},
} as Meta<typeof DarkModeToggle>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  render: () => ({
    components: { DarkModeToggle },
    template: '<DarkModeToggle />',
  }),
};

export const InHeader: Story = {
  render: () => ({
    components: { DarkModeToggle },
    template: `
      <header class="flex items-center justify-between px-4 py-3 bg-gray-100 dark:bg-gray-800 rounded">
        <span class="font-semibold">AutoBot</span>
        <DarkModeToggle />
      </header>
    `,
  }),
};

export const InToolbar: Story = {
  render: () => ({
    components: { DarkModeToggle },
    template: `
      <div class="flex items-center gap-2 p-2 border rounded">
        <button class="px-3 py-2 rounded bg-gray-200">File</button>
        <button class="px-3 py-2 rounded bg-gray-200">Edit</button>
        <div class="ml-auto">
          <DarkModeToggle />
        </div>
      </div>
    `,
  }),
};
