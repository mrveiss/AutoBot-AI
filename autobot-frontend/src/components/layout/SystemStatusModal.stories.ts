// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import SystemStatusModal from './SystemStatusModal.vue'
import { provide } from 'vue'
import { useSystemStatus } from '@/composables/useSystemStatus'
import { SYSTEM_STATUS_KEY } from '@/composables/systemStatusContext'

const meta = {
  title: 'Components/Layout/SystemStatusModal',
  component: SystemStatusModal,
  parameters: {
    layout: 'centered',
    docs: {
      description: {
        component:
          'The system-health panel on the kit BaseModal. Opens when the injected showSystemStatus is true.',
      },
    },
  },
} as Meta<typeof SystemStatusModal>

export default meta
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>

export const Open: Story = {
  args: {},
  parameters: {
    docs: { description: { story: 'Opened from the shared status state; lists every service.' } },
  },
  render: (args: Record<string, unknown>) => ({
    components: { SystemStatusModal },
    setup() {
      const status = useSystemStatus()
      status.showSystemStatus.value = true
      provide(SYSTEM_STATUS_KEY, status)
      return { args }
    },
    template: `<div><SystemStatusModal v-bind="args" /></div>`,
  }),
}
