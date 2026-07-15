// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import ToastContainer from './ToastContainer.vue';

const meta = {
  title: 'Components/UI/ToastContainer',
  component: ToastContainer,
  argTypes: {},
} as Meta<typeof ToastContainer>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

export const Default: Story = {
  render: () => ({
    components: { ToastContainer },
    setup() {
      const pushToast = async (type: 'info' | 'success' | 'warning' | 'error', message: string) => {
        const { useToast } = await import('@/composables/useToast');
        useToast().showToast(message, type);
      };
      return { pushToast };
    },
    template: `
      <div>
        <p class="mb-2 text-sm text-gray-500">
          ToastContainer renders toasts pushed via <code>useToast().showToast()</code>.
          Click a button to enqueue one.
        </p>
        <div class="flex flex-wrap gap-2 mb-4">
          <button class="px-3 py-2 bg-blue-600 text-white rounded" @click="pushToast('info', 'Informational message')">Info</button>
          <button class="px-3 py-2 bg-green-600 text-white rounded" @click="pushToast('success', 'Operation completed successfully')">Success</button>
          <button class="px-3 py-2 bg-yellow-500 text-white rounded" @click="pushToast('warning', 'Please review the configuration')">Warning</button>
          <button class="px-3 py-2 bg-red-600 text-white rounded" @click="pushToast('error', 'Something went wrong')">Error</button>
        </div>
        <ToastContainer />
      </div>
    `,
  }),
};

export const Mounted: Story = {
  render: () => ({
    components: { ToastContainer },
    template: '<ToastContainer />',
  }),
};
