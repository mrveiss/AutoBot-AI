// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import UiModeSettingsCard from './UiModeSettingsCard.vue'

const meta = {
  title: 'Components/Settings/UiModeSettingsCard',
  component: UiModeSettingsCard,
  parameters: {
    layout: 'padded',
    docs: {
      description: {
        component:
          'Preferred mode (Minimal / Full) and Start in (Last used / Minimal / Full) for Settings > Appearance.',
      },
    },
  },
} as Meta<typeof UiModeSettingsCard>

export default meta
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>

export const Default: Story = {
  args: {},
  parameters: {
    docs: { description: { story: 'Both controls write the shared useUiMode state.' } },
  },
  render: (args: Record<string, unknown>) => ({
    components: { UiModeSettingsCard },
    setup() {
      return { args }
    },
    template: `<div class="max-w-3xl"><UiModeSettingsCard v-bind="args" /></div>`,
  }),
}
