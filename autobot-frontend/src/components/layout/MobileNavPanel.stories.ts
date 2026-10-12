// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import MobileNavPanel from './MobileNavPanel.vue'

const meta = {
  title: 'Components/Layout/MobileNavPanel',
  component: MobileNavPanel,
  parameters: {
    layout: 'fullscreen',
    docs: {
      description: {
        component: 'The below-lg drawer, built from the same nav registry as the desktop header.',
      },
    },
  },
} as Meta<typeof MobileNavPanel>

export default meta
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>

export const Open: Story = {
  args: {
    open: true,
    items: [{ to: '/home', labelKey: 'nav.home', iconStroke: true, icon: 'M9 12l2 2 4-4' }],
  },
  parameters: { docs: { description: { story: 'Drawer open with one primary link.' } } },
  render: (args: Record<string, unknown>) => ({
    components: { MobileNavPanel },
    setup() {
      return { args }
    },
    template: `<div class="relative h-96 bg-autobot-bg-secondary"><MobileNavPanel v-bind="args" /></div>`,
  }),
}
