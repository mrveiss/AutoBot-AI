// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import KnowledgeVerificationQueue from './KnowledgeVerificationQueue.vue'

const meta = {
  title: 'Components/Knowledge/KnowledgeVerificationQueue',
  component: KnowledgeVerificationQueue,
  tags: ['autodocs'],
} as Meta<typeof KnowledgeVerificationQueue>

export default meta
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>

export const Default: Story = {
  args: {},
}

export const AutonomousMode: Story = {
  args: {},
}

export const CollaborativeMode: Story = {
  args: {},
}

export const WithPendingItems: Story = {
  args: {},
}

export const Empty: Story = {
  args: {},
}
