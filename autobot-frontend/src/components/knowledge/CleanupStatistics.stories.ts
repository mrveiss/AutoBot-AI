// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import CleanupStatistics from './CleanupStatistics.vue'

const meta = {
  title: 'Components/Knowledge/CleanupStatistics',
  component: CleanupStatistics,
  tags: ['autodocs'],
} as Meta<typeof CleanupStatistics>

export default meta
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>

export const Default: Story = {
  args: {},
}

export const Loading: Story = {
  args: {},
}

export const WithResults: Story = {
  args: {},
}

export const Clean: Story = {
  args: {},
}
