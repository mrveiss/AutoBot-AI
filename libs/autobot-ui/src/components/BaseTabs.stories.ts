// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import { ref } from 'vue'
import BaseTabs from './BaseTabs.vue'

const meta = {
  title: 'Kit/BaseTabs',
  component: BaseTabs,
  argTypes: {
    orientation: { control: { type: 'select' }, options: ['horizontal', 'vertical'] },
    activation: { control: { type: 'select' }, options: ['automatic', 'manual'] },
    dir: { control: { type: 'select' }, options: [undefined, 'ltr', 'rtl'] },
  },
} as Meta<typeof BaseTabs>

export default meta
type Story = StoryObj<Record<string, unknown>>

const tabs = [
  { value: 'overview', label: 'Overview' },
  { value: 'logs', label: 'Logs' },
  { value: 'locked', label: 'Locked', disabled: true },
  { value: 'settings', label: 'Settings' },
]

const render = (args: Record<string, unknown>) => ({
  components: { BaseTabs },
  setup: () => ({ args, active: ref('overview'), tabs }),
  template: `<BaseTabs v-bind="args" v-model="active" :tabs="tabs" label="Sections">
    <template #panel="{ tab }"><p>{{ tab.label }} panel</p></template>
  </BaseTabs>`,
})

export const Horizontal: Story = { args: {}, render }
export const Vertical: Story = { args: { orientation: 'vertical' }, render }
export const ManualActivation: Story = { args: { activation: 'manual' }, render }
export const RightToLeft: Story = { args: { dir: 'rtl' }, render }
