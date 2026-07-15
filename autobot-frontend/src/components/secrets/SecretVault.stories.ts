// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import SecretVault from './SecretVault.vue';

const meta = {
  title: 'Components/Secrets/SecretVault',
  component: SecretVault,
  tags: ['autodocs'],
  argTypes: {
    scope: {
      control: 'select',
      options: ['session', 'user', 'all'],
      description: 'Filters which secrets are displayed: session-scoped, user/global, or all accessible secrets.',
    },
  },
} as Meta<typeof SecretVault>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

export const AllSecrets: Story = {
  render: () => ({
    components: { SecretVault },
    template: `
      <div style="height: 600px; width: 480px; background: #1f2937;">
        <SecretVault />
      </div>
    `,
  }),
  parameters: {
    docs: {
      description: {
        story: 'Vault with no scope restriction — shows all accessible secrets. Fetches from backend on mount.',
      },
    },
  },
};

export const SessionScope: Story = {
  render: () => ({
    components: { SecretVault },
    template: `
      <div style="height: 600px; width: 480px; background: #1f2937;">
        <SecretVault scope="session" />
      </div>
    `,
  }),
  parameters: {
    docs: {
      description: {
        story: 'Vault filtered to session-scoped and chat-scoped secrets only.',
      },
    },
  },
};

export const UserScope: Story = {
  render: () => ({
    components: { SecretVault },
    template: `
      <div style="height: 600px; width: 480px; background: #1f2937;">
        <SecretVault scope="user" />
      </div>
    `,
  }),
  parameters: {
    docs: {
      description: {
        story: 'Vault filtered to user-scoped and global secrets only.',
      },
    },
  },
};
