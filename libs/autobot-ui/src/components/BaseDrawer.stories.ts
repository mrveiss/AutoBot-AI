// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import { ref } from 'vue'
import BaseDrawer from './BaseDrawer.vue'
import BaseButton from './BaseButton.vue'

const meta = {
  title: 'Kit/BaseDrawer',
  component: BaseDrawer,
  argTypes: {
    title: { control: 'text', description: 'Panel title' },
    width: { control: 'text', description: 'CSS length or px number' },
    closeOnOverlay: { control: 'boolean' },
    closeOnEsc: { control: 'boolean' },
    locked: { control: 'boolean', description: 'No backdrop click, Escape or close button' },
    flush: { control: 'boolean', description: 'Body without padding' },
  },
} as Meta<typeof BaseDrawer>

export default meta
type Story = StoryObj<Record<string, unknown>>

const render = (args: Record<string, unknown>) => ({
  components: { BaseDrawer, BaseButton },
  setup: () => ({ args, open: ref(true) }),
  template: `
    <BaseButton @click="open = true">Open drawer</BaseButton>
    <BaseDrawer v-model="open" v-bind="args" close-label="Close panel">
      <template #subtitle>node-01</template>
      <p>Panel body. It scrolls on its own while the header and footer stay put.</p>
      <template #actions><BaseButton variant="secondary" @click="open = false">Close</BaseButton></template>
    </BaseDrawer>`,
})

export const Default: Story = { args: { title: 'Node details', width: '32rem' }, render }
export const Wide: Story = { args: { title: 'Services', width: '48rem' }, render }
export const Locked: Story = { args: { title: 'Applying changes', locked: true }, render }
