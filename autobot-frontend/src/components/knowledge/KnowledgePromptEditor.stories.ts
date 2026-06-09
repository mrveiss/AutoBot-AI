// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import KnowledgePromptEditor from './KnowledgePromptEditor.vue'

const meta = {
  title: 'Components/Knowledge/KnowledgePromptEditor',
  component: KnowledgePromptEditor,
  tags: ['autodocs'],
} as Meta<typeof KnowledgePromptEditor>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const Default: Story = {
  args: {},
}

export const Loading: Story = {
  args: {},
}

export const WithPromptSelected: Story = {
  args: {},
}

export const WithUnsavedChanges: Story = {
  args: {},
}
