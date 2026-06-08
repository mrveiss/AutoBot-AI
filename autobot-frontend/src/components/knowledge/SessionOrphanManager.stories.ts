// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import SessionOrphanManager from './SessionOrphanManager.vue'

const meta = {
  title: 'Components/Knowledge/SessionOrphanManager',
  component: SessionOrphanManager,
  tags: ['autodocs'],
} as Meta<typeof SessionOrphanManager>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const Default: Story = {
  args: {},
}

export const Scanning: Story = {
  args: {},
}

export const WithOrphans: Story = {
  args: {},
}

export const Clean: Story = {
  args: {},
}
