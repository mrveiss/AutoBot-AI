// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// The one alert for both apps (#18819). Visual-regression subjects: every
// variant, both sizes, title, dismissible, bordered and an actions slot.
import type { Meta, StoryObj } from '@storybook/vue3'
import BaseAlert, { type AlertSize, type AlertVariant } from './BaseAlert.vue'

const VARIANTS: AlertVariant[] = ['success', 'info', 'warning', 'error', 'critical']
const SIZES: AlertSize[] = ['default', 'compact']

const meta = {
  title: 'Kit/BaseAlert',
  component: BaseAlert,
  argTypes: {
    variant: { control: 'select', options: VARIANTS },
    size: { control: 'select', options: SIZES },
    dismissible: { control: 'boolean' },
    bordered: { control: 'boolean' },
    icon: { control: 'boolean' },
    title: { control: 'text' },
    message: { control: 'text' },
  },
  args: { variant: 'info', size: 'default', message: 'Something worth knowing.', dismissLabel: 'Dismiss' },
} satisfies Meta<typeof BaseAlert>

export default meta
type Story = StoryObj<typeof meta>

export const Playground: Story = {}

export const Variants: Story = {
  render: () => ({
    components: { BaseAlert },
    setup: () => ({ VARIANTS }),
    template: `
      <div style="display:grid;gap:0.5rem">
        <BaseAlert v-for="v in VARIANTS" :key="v" :variant="v" :message="v + ' alert'" />
      </div>`,
  }),
}

export const Sizes: Story = {
  render: () => ({
    components: { BaseAlert },
    setup: () => ({ SIZES }),
    template: `
      <div style="display:grid;gap:0.5rem">
        <BaseAlert v-for="s in SIZES" :key="s" variant="warning" :size="s" :message="s + ' size'" />
      </div>`,
  }),
}

export const WithTitle: Story = {
  args: { variant: 'success', title: 'Saved', message: 'Your changes were stored.', bordered: true },
}

export const Dismissible: Story = {
  args: { variant: 'error', message: 'The request failed.', dismissible: true },
}

export const WithActions: Story = {
  render: () => ({
    components: { BaseAlert },
    template: `
      <BaseAlert variant="warning" title="Update available" message="A new version is ready." dismissible dismiss-label="Dismiss">
        <template #actions><button type="button">Install</button></template>
      </BaseAlert>`,
  }),
}
