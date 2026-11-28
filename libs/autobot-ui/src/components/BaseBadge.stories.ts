// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// The one badge for both apps (#14776). Each story is a visual-regression
// subject: every variant in every tone, every size, and the square, monospace
// and removable forms the main app used from its retired local fork.
import type { Meta, StoryObj } from '@storybook/vue3'
import BaseBadge, { type BadgeSize, type BadgeTone, type BadgeVariant } from './BaseBadge.vue'

const VARIANTS: BadgeVariant[] = ['neutral', 'primary', 'success', 'warning', 'error', 'info']
const TONES: BadgeTone[] = ['solid', 'subtle', 'outline']
const SIZES: BadgeSize[] = ['xs', 'sm', 'md', 'lg']

const meta = {
  title: 'Kit/BaseBadge',
  component: BaseBadge,
  argTypes: {
    variant: { control: 'select', options: VARIANTS },
    tone: { control: 'select', options: TONES },
    size: { control: 'select', options: SIZES },
    rounded: { control: 'boolean' },
    monospace: { control: 'boolean' },
    removable: { control: 'boolean' },
    label: { control: 'text' },
  },
  args: { variant: 'primary', tone: 'subtle', size: 'md', label: 'Badge' },
} satisfies Meta<typeof BaseBadge>

export default meta
type Story = StoryObj<typeof meta>

export const Playground: Story = {}

export const TonesByVariant: Story = {
  render: () => ({
    components: { BaseBadge },
    setup: () => ({ VARIANTS, TONES }),
    template: `
      <div style="display:grid;gap:0.5rem">
        <div v-for="tone in TONES" :key="tone" style="display:flex;gap:0.5rem">
          <BaseBadge v-for="variant in VARIANTS" :key="variant" :tone="tone" :variant="variant" :label="variant" />
        </div>
      </div>`,
  }),
}

export const Sizes: Story = {
  render: () => ({
    components: { BaseBadge },
    setup: () => ({ SIZES }),
    template: `<div style="display:flex;gap:0.5rem;align-items:center"><BaseBadge v-for="size in SIZES" :key="size" :size="size" variant="info" :label="size" /></div>`,
  }),
}

export const SquareMonospaceAndRemovable: Story = {
  render: () => ({
    components: { BaseBadge },
    template: `
      <div style="display:flex;gap:0.5rem;align-items:center">
        <BaseBadge monospace :rounded="false" label="v2.1.0" />
        <BaseBadge monospace :rounded="false" variant="success" label="+142ms" />
        <BaseBadge removable remove-label="Remove badge" variant="primary" label="Tag" />
      </div>`,
  }),
}
