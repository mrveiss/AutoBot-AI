// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import SectionShell from './SectionShell.vue'

const meta = {
  title: 'Kit/SectionShell',
  component: SectionShell,
} as Meta<typeof SectionShell>

export default meta
type Story = StoryObj<typeof SectionShell>

const sections = [
  {
    id: 'browse',
    label: 'Browse',
    items: [
      { id: 'browser', label: 'Browser', to: '#browser', active: true },
      { id: 'graph', label: 'Graph', to: '#graph', adv: true },
    ],
  },
]

export const Default: Story = {
  args: { navLabel: 'Knowledge Base', title: 'Knowledge Base', sections, openLabel: 'Open menu', closeLabel: 'Close menu' },
  render: (args) => ({
    components: { SectionShell },
    setup: () => ({ args }),
    template: '<SectionShell v-bind="args">Routed content</SectionShell>',
  }),
}
