// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import ChatSidebarToolbar from './ChatSidebarToolbar.vue'

const meta = {
  title: 'Components/Chat/ChatSidebarToolbar',
  component: ChatSidebarToolbar,
  tags: ['autodocs'],
  args: { search: '', selectionMode: false, selectedCount: 0 },
} satisfies Meta<typeof ChatSidebarToolbar>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {}
export const Searching: Story = { args: { search: 'npu' } }
export const SelectionMode: Story = { args: { selectionMode: true, selectedCount: 3 } }
