// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import WebResearchSettings from './WebResearchSettings.vue'

const meta = {
  title: 'Components/Knowledge/WebResearchSettings',
  component: WebResearchSettings,
  tags: ['autodocs'],
} as Meta<typeof WebResearchSettings>

export default meta
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>

export const Default: Story = {
  args: {},
}

export const Loading: Story = {
  args: {},
}

export const Enabled: Story = {
  args: {},
}

export const Disabled: Story = {
  args: {},
}

export const WithError: Story = {
  args: {},
}
