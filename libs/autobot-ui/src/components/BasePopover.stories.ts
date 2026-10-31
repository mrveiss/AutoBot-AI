// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import BasePopover from './BasePopover.vue'

const meta = {
  title: 'Kit/BasePopover',
  component: BasePopover,
  argTypes: {
    size: { control: 'select', options: ['sm', 'md', 'lg'] },
    side: { control: 'select', options: ['top', 'right', 'bottom', 'left'] },
    align: { control: 'select', options: ['start', 'center', 'end'] },
  },
} as Meta<typeof BasePopover>

export default meta
type Story = StoryObj<Record<string, unknown>>

const render = (args: Record<string, unknown>) => ({
  components: { BasePopover },
  setup: () => ({ args }),
  template: `<div style="padding:48px">
    <BasePopover v-bind="args" label="Filter options">
      <template #trigger><button type="button">Filters</button></template>
      <template #default="{ close }">
        <p>Narrow the list by status.</p>
        <button type="button" @click="close">Done</button>
      </template>
    </BasePopover>
  </div>`,
})

export const Medium: Story = { args: { size: 'md' }, render }
export const Small: Story = { args: { size: 'sm' }, render }
export const Large: Story = { args: { size: 'lg' }, render }
export const OpenAbove: Story = { args: { side: 'top' }, render }
