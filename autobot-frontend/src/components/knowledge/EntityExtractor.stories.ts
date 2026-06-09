// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import EntityExtractor from './EntityExtractor.vue'

const meta = {
  title: 'Components/Knowledge/EntityExtractor',
  component: EntityExtractor,
  tags: ['autodocs'],
} as Meta<typeof EntityExtractor>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const Default: Story = {
  args: {},
}

export const Extracting: Story = {
  args: {},
}

export const WithResults: Story = {
  args: {},
}
