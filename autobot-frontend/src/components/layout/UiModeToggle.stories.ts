// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import UiModeToggle from './UiModeToggle.vue'

const meta = {
  title: 'Components/Layout/UiModeToggle',
  component: UiModeToggle,
  parameters: {
    layout: 'centered',
    docs: {
      description: {
        component:
          'The Minimal / Full switch: a toggle button (aria-pressed) that announces the change and writes data-ui via useUiMode.',
      },
    },
  },
} as Meta<typeof UiModeToggle>

export default meta
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>

export const Default: Story = {
  args: {},
  parameters: {
    docs: { description: { story: 'Press to hide advanced features; press again to show them.' } },
  },
  render: (args: Record<string, unknown>) => ({
    components: { UiModeToggle },
    setup() {
      return { args }
    },
    template: `<div class="bg-autobot-bg-secondary p-4 rounded-md"><UiModeToggle v-bind="args" /></div>`,
  }),
}
