// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import SectionNav from './SectionNav.vue'

const meta = {
  title: 'Kit/SectionNav',
  component: SectionNav,
} as Meta<typeof SectionNav>

export default meta
type Story = StoryObj<typeof SectionNav>

const sections = [
  {
    id: 'browse',
    label: 'Browse',
    items: [
      { id: 'browser', label: 'Browser', to: '#browser', active: true },
      { id: 'graph', label: 'Graph', to: '#graph', adv: true },
    ],
  },
  {
    id: 'manage',
    label: 'Manage',
    items: [{ id: 'manage', label: 'Manage', to: '#manage' }],
  },
]

export const Default: Story = {
  args: { label: 'Knowledge Base', title: 'Knowledge Base', sections },
}

export const WithTrailingCount: Story = {
  args: { label: 'Company', sections },
  render: (args) => ({
    components: { SectionNav },
    setup: () => ({ args }),
    template: '<SectionNav v-bind="args"><template #trailing="{ item }"><span v-if="item.id === \'manage\'">3</span></template></SectionNav>',
  }),
}
