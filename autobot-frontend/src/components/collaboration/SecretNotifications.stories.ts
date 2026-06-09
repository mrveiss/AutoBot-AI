// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import SecretNotifications from './SecretNotifications.vue';

const meta = {
  title: 'Components/Collaboration/SecretNotifications',
  component: SecretNotifications,
  tags: ['autodocs'],
  argTypes: {},
} as Meta<typeof SecretNotifications>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<any>;

export const Default: Story = {
  render: () => ({
    components: { SecretNotifications },
    template: `<SecretNotifications />`,
  }),
};

export const InContainer: Story = {
  name: 'Constrained container',
  render: () => ({
    components: { SecretNotifications },
    template: `
      <div style="width: 360px;">
        <SecretNotifications />
      </div>
    `,
  }),
};

export const NarrowWidth: Story = {
  name: 'Narrow width',
  render: () => ({
    components: { SecretNotifications },
    template: `
      <div style="width: 260px;">
        <SecretNotifications />
      </div>
    `,
  }),
};

export const WideContainer: Story = {
  name: 'Wide container',
  render: () => ({
    components: { SecretNotifications },
    template: `
      <div style="width: 560px;">
        <SecretNotifications />
      </div>
    `,
  }),
};

export const InPanel: Story = {
  name: 'Embedded in panel',
  render: () => ({
    components: { SecretNotifications },
    template: `
      <div style="width: 380px; padding: 16px; background: #1e1e2e; border-radius: 8px;">
        <p style="color: #6c7086; font-size: 12px; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.05em;">Secret Activity</p>
        <SecretNotifications />
      </div>
    `,
  }),
};
