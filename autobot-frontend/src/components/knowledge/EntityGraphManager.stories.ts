// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import EntityGraphManager from './EntityGraphManager.vue'

const meta = {
  title: 'Components/Knowledge/EntityGraphManager',
  component: EntityGraphManager,
  tags: ['autodocs'],
} as Meta<typeof EntityGraphManager>

export default meta
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>

export const Default: Story = {
  args: {},
}

export const ExtractTab: Story = {
  args: {},
}

export const QueryTab: Story = {
  args: {},
}

export const StatsTab: Story = {
  args: {},
}
