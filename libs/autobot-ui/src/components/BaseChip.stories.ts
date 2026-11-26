// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { ref } from 'vue'
import type { Meta, StoryObj } from '@storybook/vue3'
import BaseChip from './BaseChip.vue'

const meta = {
  title: 'Kit/BaseChip',
  component: BaseChip,
  argTypes: { size: { control: 'select', options: ['sm', 'md'] }, pressed: { control: 'boolean' } },
  args: { pressed: false, size: 'md', disabled: false },
  render: (args) => ({
    components: { BaseChip },
    setup: () => ({ args, on: ref(args.pressed) }),
    template: '<BaseChip v-bind="args" v-model:pressed="on">Label</BaseChip>',
  }),
} satisfies Meta<typeof BaseChip>

export default meta
type Story = StoryObj<typeof meta>

export const Playground: Story = {}
export const Pressed: Story = { args: { pressed: true } }
export const Small: Story = { args: { size: 'sm' } }
export const Disabled: Story = { args: { disabled: true } }

export const WithIcon: Story = {
  render: (args) => ({
    components: { BaseChip },
    setup: () => ({ args, on: ref(true) }),
    template: `<BaseChip v-bind="args" v-model:pressed="on">
      <template #icon><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9" /></svg></template>
      Web
    </BaseChip>`,
  }),
}
