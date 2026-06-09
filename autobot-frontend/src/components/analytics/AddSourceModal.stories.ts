// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import AddSourceModal from './AddSourceModal.vue';

const meta = {
  title: 'Components/Analytics/AddSourceModal',
  component: AddSourceModal,
  tags: ['autodocs'],
  argTypes: {
    visible: { control: 'boolean' },
    source: { control: 'object' },
  },
} as Meta<typeof AddSourceModal>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    visible: true,
    source: null,
  },
};

export const EditMode: Story = {
  args: {
    visible: true,
    source: {
      id: 'src-001',
      name: 'AutoBot Backend',
      source_type: 'github',
      repo: 'mrveiss/AutoBot-AI',
      branch: 'Dev_new_gui',
      access: 'private',
      status: 'ready',
    },
  },
};

export const LocalPathMode: Story = {
  args: {
    visible: true,
    source: {
      id: 'src-002',
      name: 'Local Project',
      source_type: 'local',
      clone_path: '/opt/autobot',
      branch: 'main',
      access: 'shared',
      status: 'configured',
    },
  },
};

export const Hidden: Story = {
  args: {
    visible: false,
    source: null,
  },
};
