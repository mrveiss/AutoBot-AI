// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import { ref } from 'vue'
import BaseDropdownMenu from './BaseDropdownMenu.vue'

const meta = {
  title: 'Kit/BaseDropdownMenu',
  component: BaseDropdownMenu,
  argTypes: {
    size: { control: 'select', options: ['sm', 'md'] },
    side: { control: 'select', options: ['top', 'right', 'bottom', 'left'] },
    align: { control: 'select', options: ['start', 'center', 'end'] },
    dir: { control: 'select', options: [undefined, 'ltr', 'rtl'] },
  },
} as Meta<typeof BaseDropdownMenu>

export default meta
type Story = StoryObj<Record<string, unknown>>

const items = [
  { key: 'rename', label: 'Rename' },
  { key: 'duplicate', label: 'Duplicate', disabled: true },
  { key: 'move', label: 'Move to folder' },
  { key: 'delete', label: 'Delete', variant: 'danger', separatorBefore: true },
]

const render = (args: Record<string, unknown>) => ({
  components: { BaseDropdownMenu },
  setup: () => ({ args, items, last: ref('nothing yet') }),
  template: `<div style="padding:24px">
    <BaseDropdownMenu v-bind="args" :items="items" @select="last = $event">
      <template #trigger><button type="button">Actions</button></template>
    </BaseDropdownMenu>
    <p>Last selected: {{ last }}</p>
  </div>`,
})

export const Default: Story = { args: { size: 'md' }, render }
export const Small: Story = { args: { size: 'sm' }, render }
export const AlignedEnd: Story = { args: { align: 'end' }, render }
export const RightToLeft: Story = { args: { dir: 'rtl' }, render }
