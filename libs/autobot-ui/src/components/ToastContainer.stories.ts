// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// The one toast host for both apps (#19903). Pushes one toast per status through
// the shared useToast stack so every variant renders.
import type { Meta, StoryObj } from '@storybook/vue3'
import ToastContainer from './ToastContainer.vue'
import { useToast, type ToastType } from '../composables/useToast'

const TYPES: ToastType[] = ['success', 'info', 'warning', 'error']

const meta = {
  title: 'Kit/ToastContainer',
  component: ToastContainer,
  args: { label: 'Notifications', dismissLabel: 'Dismiss notification' },
} satisfies Meta<typeof ToastContainer>

export default meta
type Story = StoryObj<typeof meta>

export const AllStatuses: Story = {
  render: (args) => ({
    components: { ToastContainer },
    setup: () => {
      const { showToast } = useToast()
      TYPES.forEach((type) => showToast(`${type} toast`, type))
      return { args }
    },
    template: '<ToastContainer v-bind="args" />',
  }),
}
