// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import { ref } from 'vue'
import BaseSwitch from './BaseSwitch.vue'

const meta = {
  title: 'Kit/BaseSwitch',
  component: BaseSwitch,
  argTypes: {
    size: { control: 'select', options: ['sm', 'md'] },
    disabled: { control: 'boolean' },
  },
} as Meta<typeof BaseSwitch>

export default meta
type Story = StoryObj<Record<string, unknown>>

const render = (args: Record<string, unknown>) => ({
  components: { BaseSwitch },
  setup: () => ({ args, on: ref(true) }),
  template: `<label style="display:flex;gap:12px;align-items:center">
    <BaseSwitch v-model="on" v-bind="args" label="Dark mode" /> Dark mode: {{ on ? 'on' : 'off' }}
  </label>`,
})

export const Medium: Story = { args: { size: 'md' }, render }
export const Small: Story = { args: { size: 'sm' }, render }
export const Disabled: Story = { args: { disabled: true }, render }
