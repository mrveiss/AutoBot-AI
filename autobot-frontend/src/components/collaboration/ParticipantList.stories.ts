// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import ParticipantList from './ParticipantList.vue';

const meta = {
  title: 'Components/Collaboration/ParticipantList',
  component: ParticipantList,
  tags: ['autodocs'],
  argTypes: {
    compact: {
      control: 'boolean',
      description: 'Show compact view',
    },
    allowManagement: {
      control: 'boolean',
      description: 'Allow role management (owner only)',
    },
  },
} as Meta<typeof ParticipantList>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<Record<string, unknown>>;

export const Default: Story = {
  args: {
    compact: false,
    allowManagement: false,
  },
};

export const WithManagement: Story = {
  name: 'Owner with management enabled',
  args: {
    compact: false,
    allowManagement: true,
  },
};

export const Compact: Story = {
  name: 'Compact view',
  args: {
    compact: true,
    allowManagement: false,
  },
};

export const CompactWithManagement: Story = {
  name: 'Compact view with management',
  args: {
    compact: true,
    allowManagement: true,
  },
};

export const FullWidth: Story = {
  name: 'Full width container',
  render: () => ({
    components: { ParticipantList },
    template: `
      <div style="width: 400px;">
        <ParticipantList :compact="false" :allow-management="true" />
      </div>
    `,
  }),
};
