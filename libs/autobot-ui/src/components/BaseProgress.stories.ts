// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import BaseProgress, { type ProgressVariant } from './BaseProgress.vue'

const VARIANTS: ProgressVariant[] = ['neutral', 'primary', 'success', 'warning', 'error', 'info']

const meta = {
  title: 'Kit/BaseProgress',
  component: BaseProgress,
  argTypes: {
    value: { control: { type: 'range', min: 0, max: 100 } },
    variant: { control: 'select', options: VARIANTS },
    size: { control: 'select', options: ['sm', 'md'] },
  },
  args: { value: 45, label: 'Import progress', variant: 'primary', size: 'md' },
} satisfies Meta<typeof BaseProgress>

export default meta
type Story = StoryObj<typeof meta>

export const Playground: Story = {}

export const Variants: Story = {
  render: () => ({
    components: { BaseProgress },
    setup: () => ({ VARIANTS }),
    template: `<div style="display:grid;gap:0.75rem;max-width:20rem">
      <BaseProgress v-for="v in VARIANTS" :key="v" :variant="v" :value="60" :label="v" />
    </div>`,
  }),
}

export const Small: Story = { args: { size: 'sm' } }
