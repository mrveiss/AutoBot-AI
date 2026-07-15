// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import InviteUserDialog from './InviteUserDialog.vue';

const meta = {
  title: 'Components/Collaboration/InviteUserDialog',
  component: InviteUserDialog,
  tags: ['autodocs'],
  argTypes: {
    modelValue: {
      control: 'boolean',
      description: 'Whether the dialog is visible',
    },
  },
} as Meta<typeof InviteUserDialog>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<Record<string, unknown>>;

export const Open: Story = {
  name: 'Dialog open',
  args: {
    modelValue: true,
  },
};

export const Closed: Story = {
  name: 'Dialog closed',
  args: {
    modelValue: false,
  },
};

export const WithCollaboratorRole: Story = {
  name: 'Open — collaborator role selected',
  render: () => ({
    components: { InviteUserDialog },
    data() {
      return { visible: true };
    },
    template: `<InviteUserDialog v-model="visible" />`,
  }),
};

export const WithViewerRole: Story = {
  name: 'Open — viewer role context',
  render: () => ({
    components: { InviteUserDialog },
    data() {
      return { visible: true };
    },
    template: `<InviteUserDialog v-model="visible" />`,
  }),
};

export const InteractiveToggle: Story = {
  name: 'Interactive toggle',
  render: () => ({
    components: { InviteUserDialog },
    data() {
      return { visible: false };
    },
    template: `
      <div>
        <button @click="visible = true" style="padding: 8px 16px; background: #3b82f6; color: white; border-radius: 6px; border: none; cursor: pointer;">
          Open Invite Dialog
        </button>
        <InviteUserDialog v-model="visible" />
      </div>
    `,
  }),
};
