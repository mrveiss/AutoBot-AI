// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import KBSearchResultPanel from './KBSearchResultPanel.vue'

const meta = {
  title: 'Components/Knowledge/KBSearchResultPanel',
  component: KBSearchResultPanel,
  tags: ['autodocs'],
  argTypes: {
    results: { control: 'object' },
    query: { control: 'text' },
    loading: { control: 'boolean' },
    repository: { control: 'object' },
  },
} as Meta<typeof KBSearchResultPanel>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const Loading: Story = {
  args: {
    results: [],
    query: 'autobot configuration',
    loading: true,
    repository: {},
  },
}

export const WithResults: Story = {
  args: {
    results: [
      {
        document: { id: 'doc-1', title: 'AutoBot Setup Guide', category: 'system', content: 'Configuration guide for AutoBot.' },
        score: 0.95,
        snippet: 'Configuration guide for AutoBot.',
      },
      {
        document: { id: 'doc-2', title: 'Networking Overview', category: 'system', content: 'Network setup documentation.' },
        score: 0.82,
        snippet: 'Network setup documentation.',
      },
    ],
    query: 'autobot configuration',
    loading: false,
    repository: {},
  },
}

export const NoResults: Story = {
  args: {
    results: [],
    query: 'obscure search term',
    loading: false,
    repository: {},
  },
}
