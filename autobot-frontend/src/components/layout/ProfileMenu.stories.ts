// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import ProfileMenu from './ProfileMenu.vue'

const meta = {
  title: 'Components/Layout/ProfileMenu',
  component: ProfileMenu,
  parameters: {
    layout: 'centered',
    docs: {
      description: {
        component:
          'The avatar button and its dropdown: Profile settings, System status, settings and tools, admin entries, About.',
      },
    },
  },
} as Meta<typeof ProfileMenu>

export default meta
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>

export const Default: Story = {
  args: {},
  parameters: {
    docs: { description: { story: 'Visible to an authenticated user from the sm breakpoint up.' } },
  },
  render: (args: Record<string, unknown>) => ({
    components: { ProfileMenu },
    setup() {
      return { args }
    },
    template: `<div class="p-4"><ProfileMenu v-bind="args" /></div>`,
  }),
}
