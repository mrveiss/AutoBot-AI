// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import VectorizationActionButton from './VectorizationActionButton.vue'

const meta = {
  title: 'Components/Knowledge/VectorizationActionButton',
  component: VectorizationActionButton,
  tags: ['autodocs'],
  argTypes: {
    documentId: { control: 'text' },
    status: {
      control: 'select',
      options: ['vectorized', 'pending', 'failed', 'unknown'],
    },
    showLabel: { control: 'boolean' },
    compact: { control: 'boolean' },
  },
} as Meta<typeof VectorizationActionButton>

export default meta
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>

export const Vectorize: Story = {
  args: {
    documentId: 'doc-001',
    status: 'unknown',
    showLabel: true,
    compact: false,
  },
}

export const Pending: Story = {
  args: {
    documentId: 'doc-001',
    status: 'pending',
    showLabel: true,
    compact: false,
  },
}

export const Vectorized: Story = {
  args: {
    documentId: 'doc-001',
    status: 'vectorized',
    showLabel: true,
    compact: false,
  },
}

export const Failed: Story = {
  args: {
    documentId: 'doc-001',
    status: 'failed',
    showLabel: true,
    compact: false,
  },
}

export const IconOnly: Story = {
  args: {
    documentId: 'doc-001',
    status: 'unknown',
    showLabel: false,
    compact: true,
  },
}
