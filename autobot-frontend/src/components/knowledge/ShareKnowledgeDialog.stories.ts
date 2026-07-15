// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import ShareKnowledgeDialog from './ShareKnowledgeDialog.vue'

const meta = {
  title: 'Components/Knowledge/ShareKnowledgeDialog',
  component: ShareKnowledgeDialog,
  tags: ['autodocs'],
  argTypes: {
    isOpen: { control: 'boolean' },
    factId: { control: 'text' },
    factTitle: { control: 'text' },
    currentUsers: { control: 'object' },
    currentGroups: { control: 'object' },
  },
} as Meta<typeof ShareKnowledgeDialog>

export default meta
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>

export const Open: Story = {
  args: {
    isOpen: true,
    factId: 'fact-abc123',
    factTitle: 'AutoBot Configuration Guide',
    currentUsers: [],
    currentGroups: [],
  },
}

export const WithExistingAccess: Story = {
  args: {
    isOpen: true,
    factId: 'fact-abc123',
    factTitle: 'Network Setup Documentation',
    currentUsers: ['user-1', 'user-2'],
    currentGroups: ['group-engineering'],
  },
}

export const Closed: Story = {
  args: {
    isOpen: false,
    factId: 'fact-abc123',
    factTitle: 'AutoBot Configuration Guide',
    currentUsers: [],
    currentGroups: [],
  },
}
