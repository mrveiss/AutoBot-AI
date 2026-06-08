// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import BatchSelectionToolbar from './BatchSelectionToolbar.vue'

const meta = {
  title: 'Components/Knowledge/BatchSelectionToolbar',
  component: BatchSelectionToolbar,
  tags: ['autodocs'],
  argTypes: {
    selectedDocuments: { control: 'object' },
    isVectorizing: { control: 'boolean' },
  },
} as Meta<typeof BatchSelectionToolbar>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const Default: Story = {
  args: {
    selectedDocuments: [
      { id: 'doc-1', status: 'unknown' },
      { id: 'doc-2', status: 'failed' },
    ],
    isVectorizing: false,
  },
}

export const Vectorizing: Story = {
  args: {
    selectedDocuments: [
      { id: 'doc-1', status: 'unknown' },
      { id: 'doc-2', status: 'unknown' },
    ],
    isVectorizing: true,
  },
}

export const NoneEligible: Story = {
  args: {
    selectedDocuments: [
      { id: 'doc-1', status: 'vectorized' },
      { id: 'doc-2', status: 'pending' },
    ],
    isVectorizing: false,
  },
}

export const Hidden: Story = {
  args: {
    selectedDocuments: [],
    isVectorizing: false,
  },
}
