// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import { ref } from 'vue'
import KnowledgeBrowserHeader from './KnowledgeBrowserHeader.vue'

const meta = {
  title: 'Components/Knowledge/KnowledgeBrowserHeader',
  component: KnowledgeBrowserHeader,
  tags: ['autodocs'],
  argTypes: {
    query: { control: 'text' },
  },
} as Meta<typeof KnowledgeBrowserHeader>

export default meta
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>

// The search options the header's popover edits; the composable owns the real refs.
const search = {
  useRagSearch: ref(false),
  ragOptions: ref({ reformulateQuery: true, enableReranking: false, limit: 10 }),
  selectedAccessLevel: ref<string | null>(null),
  toggleAccessLevel: () => {},
  clearAccessLevelFilter: () => {},
}

export const Default: Story = {
  args: { query: '', search },
}

export const WithQuery: Story = {
  args: { query: 'fleet runbook', search },
}
