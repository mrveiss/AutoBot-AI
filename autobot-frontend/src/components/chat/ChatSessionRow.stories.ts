// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import ChatSessionRow from './ChatSessionRow.vue'

const meta = {
  title: 'Components/Chat/ChatSessionRow',
  component: ChatSessionRow,
  tags: ['autodocs'],
  args: { title: 'Fleet health check', messageCount: 14, current: false, selected: false, selectionMode: false, focused: false, folders: [] },
} satisfies Meta<typeof ChatSessionRow>

export default meta
type Story = StoryObj<typeof meta>

export const Idle: Story = {}
export const Current: Story = { args: { current: true } }
export const SelectionMode: Story = { args: { selectionMode: true, selected: true } }
export const WithFolders: Story = { args: { folders: [{ id: 'f1', name: 'Research' }, { id: 'f2', name: 'Ops' }] } }
