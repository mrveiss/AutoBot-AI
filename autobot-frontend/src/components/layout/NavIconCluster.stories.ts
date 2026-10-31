// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import NavIconCluster from './NavIconCluster.vue'

const meta = {
  title: 'Components/Layout/NavIconCluster',
  component: NavIconCluster,
  parameters: {
    layout: 'centered',
    docs: {
      description: {
        component:
          'Icon-only header controls from the nav registry: Secrets, Preferences, the mode toggle and Platform admin (shown only with service.management).',
      },
    },
  },
} as Meta<typeof NavIconCluster>

export default meta
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>

export const Default: Story = {
  args: {},
  parameters: {
    docs: { description: { story: 'Each icon has an accessible name and a tooltip.' } },
  },
  render: (args: Record<string, unknown>) => ({
    components: { NavIconCluster },
    setup() {
      return { args }
    },
    template: `<div class="bg-autobot-bg-secondary p-4 rounded-md"><NavIconCluster v-bind="args" /></div>`,
  }),
}
