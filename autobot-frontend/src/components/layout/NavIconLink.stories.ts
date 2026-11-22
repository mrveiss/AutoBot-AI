// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import NavIconLink from './NavIconLink.vue'

const meta = {
  title: 'Components/Layout/NavIconLink',
  component: NavIconLink,
  parameters: {
    layout: 'centered',
    docs: {
      description: {
        component:
          'One icon-only header control: a router link, or an external link opening a new tab, with an i18n aria-label and a kit tooltip.',
      },
    },
  },
} as Meta<typeof NavIconLink>

export default meta
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>

export const Preferences: Story = {
  args: {
    item: {
      to: '/preferences',
      labelKey: 'nav.preferences',
      ariaKey: 'nav.preferences',
      tipKey: 'nav.preferencesTip',
      iconStroke: true,
      iconViewBox: '0 0 24 24',
      iconPaths: ['M9 12a3 3 0 106 0 3 3 0 00-6 0z'],
    },
  },
  parameters: { docs: { description: { story: 'An internal entry rendered as a router link.' } } },
  render: (args: Record<string, unknown>) => ({
    components: { NavIconLink },
    setup() {
      return { args }
    },
    template: `<div class="p-4"><NavIconLink v-bind="args" /></div>`,
  }),
}
