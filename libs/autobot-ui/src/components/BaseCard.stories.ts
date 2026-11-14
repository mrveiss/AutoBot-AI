// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// The one card / panel container for both apps (#14776, #14778). Each story is a
// visual-regression subject: every frame, every text size, and the title,
// subtitle, actions and footer the main app used from its retired BaseCard
// and BasePanel forks.
import type { Meta, StoryObj } from '@storybook/vue3'
import BaseCard, { type CardSize, type CardVariant } from './BaseCard.vue'

const VARIANTS: CardVariant[] = ['default', 'bordered', 'elevated', 'flat', 'dark']
const SIZES: CardSize[] = ['sm', 'md', 'lg']

const meta = {
  title: 'Kit/BaseCard',
  component: BaseCard,
  argTypes: {
    variant: { control: 'select', options: VARIANTS },
    size: { control: 'select', options: SIZES },
    title: { control: 'text' },
    subtitle: { control: 'text' },
    flush: { control: 'boolean' },
  },
  args: { variant: 'default', size: 'md', title: 'Card title', subtitle: 'A subtitle' },
  render: (args) => ({
    components: { BaseCard },
    setup: () => ({ args }),
    template: '<BaseCard v-bind="args">Body content</BaseCard>',
  }),
} satisfies Meta<typeof BaseCard>

export default meta
type Story = StoryObj<typeof meta>

export const Playground: Story = {}

export const Variants: Story = {
  render: () => ({
    components: { BaseCard },
    setup: () => ({ VARIANTS }),
    template: `
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(14rem,1fr));gap:1rem">
        <BaseCard v-for="variant in VARIANTS" :key="variant" :variant="variant" :title="variant">Body</BaseCard>
      </div>`,
  }),
}

export const Sizes: Story = {
  render: () => ({
    components: { BaseCard },
    setup: () => ({ SIZES }),
    template: `<div style="display:grid;gap:1rem"><BaseCard v-for="size in SIZES" :key="size" :size="size" :title="size">Body text at {{ size }}</BaseCard></div>`,
  }),
}

export const HeaderActionsAndFooter: Story = {
  render: () => ({
    components: { BaseCard },
    template: `
      <BaseCard variant="elevated" title="Panel" subtitle="With actions and a footer">
        <template #actions><button type="button">Action</button></template>
        Body
        <template #footer>Footer</template>
      </BaseCard>`,
  }),
}
