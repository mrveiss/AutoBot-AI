// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import PresetManagementModal from './PresetManagementModal.vue'

const meta = {
  title: 'Components/Chat/PresetManagementModal',
  component: PresetManagementModal,
  tags: ['autodocs'],
  argTypes: {
    modelValue: { control: 'boolean' },
  },
} as Meta<typeof PresetManagementModal>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const Default: Story = {
  args: {
    modelValue: true,
  },
}

export const Closed: Story = {
  args: {
    modelValue: false,
  },
}
