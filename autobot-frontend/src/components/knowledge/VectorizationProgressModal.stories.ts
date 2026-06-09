// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import VectorizationProgressModal from './VectorizationProgressModal.vue'

const meta = {
  title: 'Components/Knowledge/VectorizationProgressModal',
  component: VectorizationProgressModal,
  tags: ['autodocs'],
  argTypes: {
    show: { control: 'boolean' },
    documentStates: { control: 'object' },
  },
} as Meta<typeof VectorizationProgressModal>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const Open: Story = {
  args: {
    show: true,
    documentStates: new Map([
      ['doc-1', { documentId: 'doc-1', name: 'README.md', status: 'pending', progress: 45 }],
      ['doc-2', { documentId: 'doc-2', name: 'SETUP.md', status: 'vectorized' }],
      ['doc-3', { documentId: 'doc-3', name: 'CONFIG.md', status: 'failed', error: 'Embedding service unavailable' }],
    ]),
  },
}

export const AllComplete: Story = {
  args: {
    show: true,
    documentStates: new Map([
      ['doc-1', { documentId: 'doc-1', name: 'README.md', status: 'vectorized' }],
      ['doc-2', { documentId: 'doc-2', name: 'SETUP.md', status: 'vectorized' }],
    ]),
  },
}

export const WithFailures: Story = {
  args: {
    show: true,
    documentStates: new Map([
      ['doc-1', { documentId: 'doc-1', name: 'README.md', status: 'failed', error: 'Timeout' }],
      ['doc-2', { documentId: 'doc-2', name: 'SETUP.md', status: 'failed', error: 'Invalid content' }],
    ]),
  },
}

export const Empty: Story = {
  args: {
    show: true,
    documentStates: new Map(),
  },
}

export const Closed: Story = {
  args: {
    show: false,
    documentStates: new Map(),
  },
}
