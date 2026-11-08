// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// The one button for both apps (#18849). Each story is a visual-regression
// subject: every variant, every size, the icon-left slot, loading, disabled
// and the link form (rendered through `as`, the kit never imports a router).
import type { Meta, StoryObj } from '@storybook/vue3'
import BaseButton, { type ButtonSize, type ButtonVariant } from './BaseButton.vue'

const VARIANTS: ButtonVariant[] = [
  'primary', 'secondary', 'ghost', 'error', 'success', 'warning', 'info', 'outline', 'link',
]
const SIZES: ButtonSize[] = ['xs', 'sm', 'md', 'lg', 'xl']

const meta = {
  title: 'Kit/BaseButton',
  component: BaseButton,
  argTypes: {
    variant: { control: 'select', options: VARIANTS },
    size: { control: 'select', options: SIZES },
    type: { control: 'select', options: ['button', 'submit', 'reset'] },
    as: { control: 'text' },
    disabled: { control: 'boolean' },
    loading: { control: 'boolean' },
    block: { control: 'boolean' },
  },
  args: { variant: 'primary', size: 'md' },
  render: (args) => ({
    components: { BaseButton },
    setup: () => ({ args }),
    template: '<BaseButton v-bind="args">Button</BaseButton>',
  }),
} satisfies Meta<typeof BaseButton>

export default meta
type Story = StoryObj<typeof meta>

export const Playground: Story = {}

export const Variants: Story = {
  render: () => ({
    components: { BaseButton },
    setup: () => ({ VARIANTS }),
    template: `
      <div style="display:flex;flex-wrap:wrap;gap:0.5rem">
        <BaseButton v-for="variant in VARIANTS" :key="variant" :variant="variant">{{ variant }}</BaseButton>
      </div>`,
  }),
}

export const Sizes: Story = {
  render: () => ({
    components: { BaseButton },
    setup: () => ({ SIZES }),
    template: `
      <div style="display:flex;align-items:center;gap:0.5rem">
        <BaseButton v-for="size in SIZES" :key="size" :size="size">{{ size }}</BaseButton>
      </div>`,
  }),
}

export const IconLeft: Story = {
  render: () => ({
    components: { BaseButton },
    template: `
      <BaseButton variant="secondary">
        <template #icon-left><span aria-hidden="true">+</span></template>
        Add
      </BaseButton>`,
  }),
}

export const Loading: Story = {
  render: () => ({
    components: { BaseButton },
    template: `
      <BaseButton loading>
        <template #icon-left><span aria-hidden="true">+</span></template>
        Saving
      </BaseButton>`,
  }),
}

export const Disabled: Story = { args: { disabled: true } }

export const Block: Story = { args: { block: true } }

export const Link: Story = {
  render: () => ({
    components: { BaseButton },
    template: '<BaseButton as="a" href="#docs" variant="link">Documentation</BaseButton>',
  }),
}
