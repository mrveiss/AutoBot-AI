// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import TopNavLinks from './TopNavLinks.vue'

const meta = {
  title: 'Components/Layout/TopNavLinks',
  component: TopNavLinks,
  parameters: {
    layout: 'fullscreen',
    docs: {
      description: {
        component:
          'The primary link rail with a 2px accent underline on the active link. Advanced links drop out in Minimal mode; overflow goes to the More menu.',
      },
    },
  },
} as Meta<typeof TopNavLinks>

export default meta
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>

export const Default: Story = {
  args: {
    items: [
      {
        to: '/home',
        labelKey: 'nav.home',
        iconViewBox: '0 0 24 24',
        iconStroke: true,
        icon: 'M9 12l2 2 4-4',
      },
      { to: '/chat', labelKey: 'nav.chat', iconStroke: true, icon: 'M4 6h16' },
      {
        to: '/analytics',
        labelKey: 'nav.analytics',
        adv: true,
        iconStroke: true,
        icon: 'M4 18h16',
      },
    ],
  },
  parameters: { docs: { description: { story: 'Three links; Analytics is advanced.' } } },
  render: (args: Record<string, unknown>) => ({
    components: { TopNavLinks },
    setup() {
      return { args }
    },
    template: `<div class="bg-autobot-bg-secondary px-6"><TopNavLinks v-bind="args" /></div>`,
  }),
}
