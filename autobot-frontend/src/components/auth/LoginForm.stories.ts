// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import LoginForm from './LoginForm.vue';

const meta = {
  title: 'Components/Auth/LoginForm',
  component: LoginForm,
} as Meta<typeof LoginForm>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

export const Default: Story = {
  render: () => ({
    components: { LoginForm },
    template: `
      <div class="min-h-screen flex items-center justify-center bg-gray-100">
        <div class="w-full max-w-md">
          <LoginForm />
        </div>
      </div>
    `,
  }),
};

export const CompactView: Story = {
  render: () => ({
    components: { LoginForm },
    template: '<LoginForm class="p-4 border rounded-lg" />',
  }),
};
