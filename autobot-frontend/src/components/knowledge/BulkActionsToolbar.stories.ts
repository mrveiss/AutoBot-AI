// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import BulkActionsToolbar from './BulkActionsToolbar.vue'

const meta = {
  title: 'Components/Knowledge/BulkActionsToolbar',
  component: BulkActionsToolbar,
  tags: ['autodocs'],
  argTypes: {
    selectedCount: { control: 'number' },
    totalCount: { control: 'number' },
    pageCount: { control: 'number' },
    allPageSelected: { control: 'boolean' },
    allMatchingSelected: { control: 'boolean' },
  },
} as Meta<typeof BulkActionsToolbar>

export default meta
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>

export const Default: Story = {
  args: {
    selectedCount: 5,
    totalCount: 120,
    pageCount: 20,
    allPageSelected: false,
    allMatchingSelected: false,
  },
}

export const PageSelected: Story = {
  args: {
    selectedCount: 20,
    totalCount: 120,
    pageCount: 20,
    allPageSelected: true,
    allMatchingSelected: false,
  },
}

export const AllMatchingSelected: Story = {
  args: {
    selectedCount: 120,
    totalCount: 120,
    pageCount: 20,
    allPageSelected: true,
    allMatchingSelected: true,
  },
}

export const NoneSelected: Story = {
  args: {
    selectedCount: 0,
    totalCount: 120,
    pageCount: 20,
    allPageSelected: false,
    allMatchingSelected: false,
  },
}
