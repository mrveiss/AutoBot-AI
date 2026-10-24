// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import { ref } from 'vue'
import BaseAccordion from './BaseAccordion.vue'

const meta = {
  title: 'Kit/BaseAccordion',
  component: BaseAccordion,
  argTypes: {
    type: { control: { type: 'select' }, options: ['single', 'multiple'] },
    collapsible: { control: 'boolean' },
    dir: { control: { type: 'select' }, options: [undefined, 'ltr', 'rtl'] },
  },
} as Meta<typeof BaseAccordion>

export default meta
type Story = StoryObj<Record<string, unknown>>

const items = [
  { value: 'general', label: 'General' },
  { value: 'network', label: 'Network' },
  { value: 'danger', label: 'Danger zone', disabled: true },
]

const render = (args: Record<string, unknown>) => ({
  components: { BaseAccordion },
  setup: () => ({ args, open: ref(args.type === 'multiple' ? ['general'] : 'general'), items }),
  template: `<BaseAccordion v-bind="args" v-model="open" :items="items">
    <template #panel="{ item }"><p>{{ item.label }} settings</p></template>
  </BaseAccordion>`,
})

export const Single: Story = { args: { type: 'single' }, render }
export const Multiple: Story = { args: { type: 'multiple' }, render }
export const RightToLeft: Story = { args: { dir: 'rtl' }, render }
