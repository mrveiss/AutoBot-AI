// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import ConfirmDialog from './ConfirmDialog.vue';

const meta = {
  title: 'Components/UI/ConfirmDialog',
  component: ConfirmDialog,
  argTypes: {},
} as Meta<typeof ConfirmDialog>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  render: () => ({
    components: { ConfirmDialog },
    setup() {
      // ConfirmDialog reads visibility/options from useConfirmDialog composable.
      // In Storybook the composable starts hidden — this story demonstrates the
      // mounted component; trigger via the composable in real use.
      return {};
    },
    template: `
      <div>
        <p class="mb-2 text-sm text-gray-500">
          ConfirmDialog is driven by <code>useConfirmDialog().confirm()</code>.
          Click below to invoke it.
        </p>
        <button
          class="px-4 py-2 bg-blue-600 text-white rounded"
          @click="async () => {
            const { useConfirmDialog } = await import('@/composables/useConfirmDialog');
            const { confirm } = useConfirmDialog();
            await confirm({ title: 'Delete item?', message: 'This action cannot be undone.' });
          }"
        >
          Open ConfirmDialog
        </button>
        <ConfirmDialog />
      </div>
    `,
  }),
};

export const Mounted: Story = {
  render: () => ({
    components: { ConfirmDialog },
    template: '<ConfirmDialog />',
  }),
};
