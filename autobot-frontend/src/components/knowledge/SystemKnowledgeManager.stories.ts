// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import SystemKnowledgeManager from './SystemKnowledgeManager.vue'

const meta = {
  title: 'Components/Knowledge/SystemKnowledgeManager',
  component: SystemKnowledgeManager,
  tags: ['autodocs'],
} as Meta<typeof SystemKnowledgeManager>

export default meta
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>

export const Default: Story = {
  args: {},
}

export const Loading: Story = {
  args: {},
}

export const WithStats: Story = {
  args: {},
}
