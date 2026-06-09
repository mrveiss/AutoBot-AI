// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import KnowledgeStats from './KnowledgeStats.vue'

const meta = {
  title: 'Components/Knowledge/KnowledgeStats',
  component: KnowledgeStats,
  tags: ['autodocs'],
} as Meta<typeof KnowledgeStats>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const Default: Story = {
  args: {},
}

export const Loading: Story = {
  args: {},
}

export const WithVectorStats: Story = {
  args: {},
}

export const NeedsVectorization: Story = {
  args: {},
}
