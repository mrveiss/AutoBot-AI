// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import PluginInstallModal from './PluginInstallModal.vue';

const meta = {
  title: 'Components/Plugins/PluginInstallModal',
  component: PluginInstallModal,
  argTypes: {
    open: {
      control: 'boolean',
      description: 'Controls whether the modal is visible',
    },
  },
} as Meta<typeof PluginInstallModal>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const OpenZipTab: Story = {
  name: 'Open — ZIP tab',
  args: {
    open: true,
  },
  render: (args: any) => ({
    components: { PluginInstallModal },
    setup() {
      return { args };
    },
    template: `
      <div style="position: relative; width: 100%; height: 600px;">
        <p class="mb-4 text-sm text-gray-500">
          PluginInstallModal opens on the ZIP tab by default.
          Users can pick a .zip archive from their filesystem to install a plugin.
        </p>
        <PluginInstallModal :open="args.open" @close="args.open = false" @installed="() => {}" />
      </div>
    `,
  }),
};

export const OpenGitTab: Story = {
  name: 'Open — Git tab',
  args: {
    open: true,
  },
  render: (args: any) => ({
    components: { PluginInstallModal },
    setup() {
      return { args };
    },
    template: `
      <div style="position: relative; width: 100%; height: 600px;">
        <p class="mb-4 text-sm text-gray-500">
          The Git tab lets users install a plugin directly from a Git repository URL
          with an optional branch/tag/commit ref.
        </p>
        <!--
          The modal initialises activeTab to 'zip' on open.
          To pre-select 'git' in Storybook, click the Git tab after the modal mounts.
        -->
        <PluginInstallModal :open="args.open" @close="args.open = false" @installed="() => {}" />
      </div>
    `,
  }),
};

export const Closed: Story = {
  args: {
    open: false,
  },
  render: (args: any) => ({
    components: { PluginInstallModal },
    setup() {
      return { args };
    },
    template: `
      <div>
        <p class="mb-4 text-sm text-gray-500">
          When <code>open</code> is false the modal is hidden — nothing is rendered to the DOM.
        </p>
        <PluginInstallModal :open="args.open" @close="args.open = false" @installed="() => {}" />
        <p class="mt-4 text-sm text-gray-400">Modal is hidden in this state.</p>
      </div>
    `,
  }),
};
