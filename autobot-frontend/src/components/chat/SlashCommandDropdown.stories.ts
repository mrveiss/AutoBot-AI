// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import SlashCommandDropdown from './SlashCommandDropdown.vue'

const meta = {
  title: 'Components/Chat/SlashCommandDropdown',
  component: SlashCommandDropdown,
  tags: ['autodocs'],
  argTypes: {
    show: { control: 'boolean' },
    selectedIndex: { control: 'number' },
  },
} as Meta<typeof SlashCommandDropdown>

export default meta
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>

const samplePresets = [
  { id: '1', name: 'standup', description: 'Daily standup summary', content: 'Give me a standup summary...', createdAt: '2026-01-01T00:00:00Z', updatedAt: '2026-01-01T00:00:00Z' },
  { id: '2', name: 'summarize', description: 'Summarize the conversation', content: 'Please summarize our conversation so far.', createdAt: '2026-01-01T00:00:00Z', updatedAt: '2026-01-01T00:00:00Z' },
  { id: '3', name: 'explain', description: 'Explain a concept in detail', content: 'Please explain the following concept in detail:', createdAt: '2026-01-01T00:00:00Z', updatedAt: '2026-01-01T00:00:00Z' },
]

export const Default: Story = {
  args: {
    show: true,
    suggestions: samplePresets,
    selectedIndex: 0,
    anchorEl: null,
  },
}

export const SecondItemSelected: Story = {
  args: {
    show: true,
    suggestions: samplePresets,
    selectedIndex: 1,
    anchorEl: null,
  },
}

export const SingleSuggestion: Story = {
  args: {
    show: true,
    suggestions: [samplePresets[0]],
    selectedIndex: 0,
    anchorEl: null,
  },
}

export const Hidden: Story = {
  args: {
    show: false,
    suggestions: samplePresets,
    selectedIndex: 0,
    anchorEl: null,
  },
}
