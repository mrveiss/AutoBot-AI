// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import { ref } from 'vue'
import BaseTabs from './BaseTabs.vue'

const meta = {
  title: 'Kit/BaseTabs',
  component: BaseTabs,
  argTypes: {
    variant: { control: 'select', options: ['underline', 'pill'] },
    size: { control: 'select', options: ['sm', 'md'] },
    orientation: { control: 'select', options: ['horizontal', 'vertical'] },
    activationMode: { control: 'select', options: ['automatic', 'manual'] },
    dir: { control: 'select', options: [undefined, 'ltr', 'rtl'] },
  },
} as Meta<typeof BaseTabs>

export default meta
type Story = StoryObj<Record<string, unknown>>

const items = [
  { value: 'overview', label: 'Overview' },
  { value: 'activity', label: 'Activity' },
  { value: 'archived', label: 'Archived', disabled: true },
  { value: 'settings', label: 'Settings' },
]

const render = (args: Record<string, unknown>) => ({
  components: { BaseTabs },
  setup: () => ({ args, items, current: ref('overview') }),
  template: `<BaseTabs v-model="current" v-bind="args" :items="items" label="Project sections">
    <template #panel-overview>Overview panel</template>
    <template #panel-activity>Activity panel</template>
    <template #panel-settings>Settings panel</template>
  </BaseTabs>`,
})

export const Underline: Story = { args: { variant: 'underline' }, render }
export const Pill: Story = { args: { variant: 'pill' }, render }
export const Small: Story = { args: { size: 'sm' }, render }
export const Vertical: Story = { args: { orientation: 'vertical' }, render }
export const ManualActivation: Story = { args: { activationMode: 'manual' }, render }
export const RightToLeft: Story = { args: { dir: 'rtl' }, render }
