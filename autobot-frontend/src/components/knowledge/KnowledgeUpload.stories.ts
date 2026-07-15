// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import KnowledgeUpload from './KnowledgeUpload.vue'

const meta = {
  title: 'Components/Knowledge/KnowledgeUpload',
  component: KnowledgeUpload,
  tags: ['autodocs'],
} as Meta<typeof KnowledgeUpload>

export default meta
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>

export const Default: Story = {
  args: {},
}

export const Uploading: Story = {
  args: {},
}

export const Success: Story = {
  args: {},
}

export const WithError: Story = {
  args: {},
}
