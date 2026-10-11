// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import AppHeader from './AppHeader.vue'
import { provide } from 'vue'
import { useSystemStatus } from '@/composables/useSystemStatus'
import { SYSTEM_STATUS_KEY } from '@/composables/systemStatusContext'

const meta = {
  title: 'Components/Layout/AppHeader',
  component: AppHeader,
  parameters: {
    layout: 'fullscreen',
    docs: {
      description: {
        component:
          'The application top bar: kit brand mark linking Home, primary links, icon cluster, profile menu and the mobile drawer. Reads the shared system status via inject.',
      },
    },
  },
} as Meta<typeof AppHeader>

export default meta
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>

export const Default: Story = {
  args: {},
  parameters: { docs: { description: { story: 'Full interface: every link and icon is shown.' } } },
  render: (args: Record<string, unknown>) => ({
    components: { AppHeader },
    setup() {
      provide(SYSTEM_STATUS_KEY, useSystemStatus())
      return { args }
    },
    template: `<AppHeader v-bind="args" />`,
  }),
}
