// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import { ref } from 'vue';
import ShareSecretDialog from './ShareSecretDialog.vue';

const meta = {
  title: 'Components/Secrets/ShareSecretDialog',
  component: ShareSecretDialog,
  tags: ['autodocs'],
  argTypes: {
    modelValue: {
      control: 'boolean',
      description: 'Controls dialog open/close state (v-model)',
    },
    secretId: {
      control: 'text',
      description: 'ID of the secret being shared',
    },
    secretName: {
      control: 'text',
      description: 'Display name of the secret',
    },
    secretType: {
      control: 'text',
      description: 'Type of the secret (e.g. api_key, password, ssh_key)',
    },
  },
} as Meta<typeof ShareSecretDialog>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Open: Story = {
  render: () => ({
    components: { ShareSecretDialog },
    setup() {
      const open = ref(true);
      return { open };
    },
    template: `
      <div style="min-height: 400px; background: #1f2937; position: relative;">
        <ShareSecretDialog
          v-model="open"
          secret-id="secret_abc123"
          secret-name="Production API Key"
          secret-type="api_key"
        />
      </div>
    `,
  }),
  parameters: {
    docs: {
      description: {
        story: 'Dialog in the open state, ready for participant selection and expiry configuration.',
      },
    },
  },
};

export const Closed: Story = {
  render: () => ({
    components: { ShareSecretDialog },
    setup() {
      const open = ref(false);
      return { open };
    },
    template: `
      <div style="min-height: 200px; background: #1f2937; display: flex; align-items: center; justify-content: center;">
        <p style="color: #9ca3af; font-size: 14px;">Dialog is closed — toggle modelValue to open it.</p>
        <ShareSecretDialog
          v-model="open"
          secret-id="secret_abc123"
          secret-name="Production API Key"
          secret-type="api_key"
        />
      </div>
    `,
  }),
  parameters: {
    docs: {
      description: {
        story: 'Dialog in the closed state. The component renders nothing visible; backdrop and panel are hidden.',
      },
    },
  },
};

export const OpenWithPasswordSecret: Story = {
  render: () => ({
    components: { ShareSecretDialog },
    setup() {
      const open = ref(true);
      return { open };
    },
    template: `
      <div style="min-height: 400px; background: #1f2937; position: relative;">
        <ShareSecretDialog
          v-model="open"
          secret-id="secret_def456"
          secret-name="Database Root Password"
          secret-type="password"
        />
      </div>
    `,
  }),
  parameters: {
    docs: {
      description: {
        story: 'Dialog open for a password-type secret, showing how the secretType label renders differently.',
      },
    },
  },
};
