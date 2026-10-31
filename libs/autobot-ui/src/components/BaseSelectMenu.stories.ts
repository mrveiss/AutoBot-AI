// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import { ref } from 'vue'
import BaseSelectMenu from './BaseSelectMenu.vue'

const meta = {
  title: 'Kit/BaseSelectMenu',
  component: BaseSelectMenu,
  argTypes: {
    size: { control: 'select', options: ['sm', 'md', 'lg'] },
    variant: { control: 'select', options: ['default', 'subtle'] },
    disabled: { control: 'boolean' },
    dir: { control: 'select', options: [undefined, 'ltr', 'rtl'] },
  },
} as Meta<typeof BaseSelectMenu>

export default meta
type Story = StoryObj<Record<string, unknown>>

const options = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High', disabled: true },
  { value: 'critical', label: 'Critical' },
]

const render = (args: Record<string, unknown>) => ({
  components: { BaseSelectMenu },
  setup: () => ({ args, options, chosen: ref<string | undefined>(undefined) }),
  template: `<div style="padding:24px">
    <BaseSelectMenu v-model="chosen" v-bind="args" :options="options" label="Priority" placeholder="Choose a priority" />
    <p>Chosen: {{ chosen ?? 'nothing yet' }}</p>
  </div>`,
})

export const Medium: Story = { args: { size: 'md' }, render }
export const Small: Story = { args: { size: 'sm' }, render }
export const Large: Story = { args: { size: 'lg' }, render }
export const Subtle: Story = { args: { variant: 'subtle' }, render }
export const Disabled: Story = { args: { disabled: true }, render }
export const RightToLeft: Story = { args: { dir: 'rtl' }, render }
