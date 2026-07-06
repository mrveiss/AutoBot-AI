// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import KnowledgePersistenceDialog from './KnowledgePersistenceDialog.vue'

const meta = {
  title: 'Components/Knowledge/KnowledgePersistenceDialog',
  component: KnowledgePersistenceDialog,
  tags: ['autodocs'],
} as Meta<typeof KnowledgePersistenceDialog>

export default meta
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>

export const Default: Story = {
  args: {},
}

export const WithItems: Story = {
  args: {},
}

export const Loading: Story = {
  args: {},
}
