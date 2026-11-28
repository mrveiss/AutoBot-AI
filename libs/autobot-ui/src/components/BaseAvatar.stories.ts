// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import BaseAvatar from './BaseAvatar.vue'

const meta = {
  title: 'Kit/BaseAvatar',
  component: BaseAvatar,
  argTypes: {
    size: { control: 'select', options: ['xs', 'sm', 'md', 'lg'] },
    variant: { control: 'select', options: ['neutral', 'primary'] },
    status: { control: 'select', options: [undefined, 'online', 'away', 'offline'] },
    ring: { control: 'boolean' },
  },
  args: { name: 'Ada Lovelace' },
} as Meta<typeof BaseAvatar>

export default meta
type Story = StoryObj<typeof meta>

export const Neutral: Story = {}
export const Primary: Story = { args: { variant: 'primary' } }
export const WithStatus: Story = { args: { status: 'online', size: 'lg' } }
export const Stacked: Story = {
  render: () => ({
    components: { BaseAvatar },
    template: `<div style="display:flex">
      <BaseAvatar v-for="n in ['Ada Lovelace', 'Grace Hopper', 'Alan Turing']" :key="n" :name="n" size="sm" ring style="margin-left:-6px" />
    </div>`,
  }),
}
