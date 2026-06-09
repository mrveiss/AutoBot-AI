// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import KnowledgeGraph from './KnowledgeGraph.vue'

const meta = {
  title: 'Components/Knowledge/KnowledgeGraph',
  component: KnowledgeGraph,
  tags: ['autodocs'],
} as Meta<typeof KnowledgeGraph>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const Default: Story = {
  args: {},
}

export const Loading: Story = {
  args: {},
}

export const Empty: Story = {
  args: {},
}

export const Mode3D: Story = {
  args: {},
}
