// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import BaseAccordion from './BaseAccordion.vue'

const meta = {
  title: 'Kit/BaseAccordion',
  component: BaseAccordion,
  argTypes: {
    type: { control: 'select', options: ['single', 'multiple'] },
    variant: { control: 'select', options: ['default', 'flush'] },
    size: { control: 'select', options: ['sm', 'md'] },
    orientation: { control: 'select', options: ['vertical', 'horizontal'] },
    collapsible: { control: 'boolean' },
    dir: { control: 'select', options: [undefined, 'ltr', 'rtl'] },
  },
} as Meta<typeof BaseAccordion>

export default meta
type Story = StoryObj<Record<string, unknown>>

const items = [
  { value: 'general', label: 'General' },
  { value: 'security', label: 'Security' },
  { value: 'billing', label: 'Billing', disabled: true },
  { value: 'advanced', label: 'Advanced' },
]

const render = (args: Record<string, unknown>) => ({
  components: { BaseAccordion },
  setup: () => ({ args, items }),
  template: `<BaseAccordion v-bind="args" :items="items">
    <template #panel-general>General settings.</template>
    <template #panel-security>Security settings.</template>
    <template #panel-advanced>Advanced settings.</template>
  </BaseAccordion>`,
})

export const Single: Story = { args: { type: 'single', defaultValue: 'general' }, render }
export const Multiple: Story = { args: { type: 'multiple', defaultValue: ['general', 'security'] }, render }
export const Flush: Story = { args: { variant: 'flush' }, render }
export const Small: Story = { args: { size: 'sm' }, render }
export const RightToLeft: Story = { args: { dir: 'rtl' }, render }
