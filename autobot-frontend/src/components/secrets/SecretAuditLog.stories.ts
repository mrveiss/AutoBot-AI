// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import SecretAuditLog from './SecretAuditLog.vue';

const meta = {
  title: 'Components/Secrets/SecretAuditLog',
  component: SecretAuditLog,
  tags: ['autodocs'],
} as Meta<typeof SecretAuditLog>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

export const Default: Story = {
  render: () => ({
    components: { SecretAuditLog },
    template: `
      <div style="height: 500px; width: 700px; background: #1f2937;">
        <SecretAuditLog />
      </div>
    `,
  }),
  parameters: {
    docs: {
      description: {
        story: 'Default audit log showing all secret operations. Fetches real data from the backend on mount.',
      },
    },
  },
};

export const CompactContainer: Story = {
  render: () => ({
    components: { SecretAuditLog },
    template: `
      <div style="height: 300px; width: 400px; background: #1f2937;">
        <SecretAuditLog />
      </div>
    `,
  }),
  parameters: {
    docs: {
      description: {
        story: 'Audit log in a compact container, demonstrating the flex layout adapts to smaller heights.',
      },
    },
  },
};
