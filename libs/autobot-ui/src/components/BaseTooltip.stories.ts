// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import BaseTooltip from './BaseTooltip.vue'

const meta = {
  title: 'Kit/BaseTooltip',
  component: BaseTooltip,
  argTypes: {
    placement: { control: 'select', options: ['top', 'bottom', 'left', 'right'] },
    disabled: { control: 'boolean' },
  },
} as Meta<typeof BaseTooltip>

export default meta
type Story = StoryObj<Record<string, unknown>>

const render = (args: Record<string, unknown>) => ({
  components: { BaseTooltip },
  setup: () => ({ args }),
  template: `<div style="padding:64px">
    <BaseTooltip v-bind="args">
      <template #default="{ describedby }">
        <button type="button" :aria-describedby="describedby">Hover or focus me</button>
      </template>
    </BaseTooltip>
  </div>`,
})

export const Bottom: Story = { args: { text: 'Shown below the trigger', placement: 'bottom' }, render }
export const Top: Story = { args: { text: 'Shown above the trigger', placement: 'top' }, render }
export const Left: Story = { args: { text: 'Shown to the left', placement: 'left' }, render }
export const Right: Story = { args: { text: 'Shown to the right', placement: 'right' }, render }
export const Disabled: Story = { args: { text: 'Never shown', disabled: true }, render }

export const RichContent: Story = {
  render: (args: Record<string, unknown>) => ({
    components: { BaseTooltip },
    setup: () => ({ args }),
    template: `<div style="padding:64px">
      <BaseTooltip v-bind="args">
        <template #default="{ describedby }">
          <button type="button" :aria-describedby="describedby">Rich content</button>
        </template>
        <template #content><strong>Title</strong><br />Supporting detail</template>
      </BaseTooltip>
    </div>`,
  }),
}
