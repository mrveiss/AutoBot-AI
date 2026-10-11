// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import NavItemIcon from './NavItemIcon.vue'

const meta = {
  title: 'Components/Layout/NavItemIcon',
  component: NavItemIcon,
  parameters: {
    layout: 'centered',
    docs: {
      description: {
        component:
          'Decorative SVG for a nav-registry entry; the label or aria-label sits on the parent.',
      },
    },
  },
} as Meta<typeof NavItemIcon>

export default meta
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>

export const Stroke: Story = {
  args: {
    item: {
      iconStroke: true,
      iconViewBox: '0 0 24 24',
      icon: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z',
    },
  },
  parameters: { docs: { description: { story: 'A stroked 24-grid icon.' } } },
  render: (args: Record<string, unknown>) => ({
    components: { NavItemIcon },
    setup() {
      return { args }
    },
    template: `<NavItemIcon v-bind="args" class="h-8 w-8" />`,
  }),
}
