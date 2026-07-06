// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3'
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3'
import PushNotificationSettingsPanel from './PushNotificationSettingsPanel.vue'

type Story = StoryObj<Record<string, unknown>>

const meta = {
  title: 'Components/Settings/PushNotificationSettingsPanel',
  component: PushNotificationSettingsPanel,
  tags: ['autodocs'],
  argTypes: {},
} as Meta<typeof PushNotificationSettingsPanel>

export default meta

export const Default: Story = {
  name: 'Default (browser-supported)',
  render: () => ({
    components: { PushNotificationSettingsPanel },
    template: `
      <div style="max-width:640px;padding:24px">
        <PushNotificationSettingsPanel />
      </div>
    `,
  }),
}

export const InSettingsContainer: Story = {
  name: 'Inside Settings Container',
  render: () => ({
    components: { PushNotificationSettingsPanel },
    template: `
      <div style="max-width:800px;background:var(--bg-secondary);border-radius:12px;border:1px solid var(--border-default);overflow:hidden">
        <div style="padding:24px 28px;border-bottom:1px solid var(--border-default)">
          <h2 style="margin:0;font-size:1.1rem;font-weight:600">Notifications</h2>
          <p style="margin:4px 0 0;font-size:0.875rem;color:var(--text-secondary)">Manage browser push notifications for this device.</p>
        </div>
        <div style="padding:24px 28px">
          <PushNotificationSettingsPanel />
        </div>
      </div>
    `,
  }),
}
