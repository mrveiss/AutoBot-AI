// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import KnowledgeResearchPanel from './KnowledgeResearchPanel.vue'

const meta = {
  title: 'Components/Knowledge/KnowledgeResearchPanel',
  component: KnowledgeResearchPanel,
  tags: ['autodocs'],
} as Meta<typeof KnowledgeResearchPanel>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const Default: Story = {
  args: {},
}

export const Researching: Story = {
  args: {},
}

export const WithResults: Story = {
  args: {},
}
