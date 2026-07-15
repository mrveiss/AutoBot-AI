// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import QualityScoreBadge from './QualityScoreBadge.vue'

const meta = {
  title: 'Components/Knowledge/QualityScoreBadge',
  component: QualityScoreBadge,
  tags: ['autodocs'],
  argTypes: {
    score: { control: { type: 'range', min: 0, max: 1, step: 0.01 } },
  },
} as Meta<typeof QualityScoreBadge>

export default meta
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>

export const High: Story = {
  args: {
    score: 0.95,
  },
}

export const Medium: Story = {
  args: {
    score: 0.65,
  },
}

export const Low: Story = {
  args: {
    score: 0.25,
  },
}

export const Null: Story = {
  args: {
    score: null,
  },
}

export const Undefined: Story = {
  args: {
    score: undefined,
  },
}
