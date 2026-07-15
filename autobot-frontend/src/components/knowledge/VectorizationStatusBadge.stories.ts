// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import VectorizationStatusBadge from './VectorizationStatusBadge.vue'

const meta = {
  title: 'Components/Knowledge/VectorizationStatusBadge',
  component: VectorizationStatusBadge,
  tags: ['autodocs'],
  argTypes: {
    status: {
      control: 'select',
      options: ['vectorized', 'pending', 'failed', 'unknown'],
    },
    showLabel: { control: 'boolean' },
    compact: { control: 'boolean' },
  },
} as Meta<typeof VectorizationStatusBadge>

export default meta
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>

export const Vectorized: Story = {
  args: {
    status: 'vectorized',
    showLabel: true,
    compact: false,
  },
}

export const Pending: Story = {
  args: {
    status: 'pending',
    showLabel: true,
    compact: false,
  },
}

export const Failed: Story = {
  args: {
    status: 'failed',
    showLabel: true,
    compact: false,
  },
}

export const Unknown: Story = {
  args: {
    status: 'unknown',
    showLabel: true,
    compact: false,
  },
}

export const Compact: Story = {
  args: {
    status: 'vectorized',
    showLabel: false,
    compact: true,
  },
}
