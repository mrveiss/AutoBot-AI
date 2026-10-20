// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// The one text input for both apps (#14778). Each story is a visual-regression
// subject: the plain field, helper and error text, every size, the required,
// disabled and readonly states, the prefix/suffix slots and the clear button.
import type { Meta, StoryObj } from '@storybook/vue3'
import BaseInput, { type InputSize, type InputType } from './BaseInput.vue'

const SIZES: InputSize[] = ['sm', 'md', 'lg']
const TYPES: InputType[] = ['text', 'email', 'password', 'search', 'tel', 'url']

const meta = {
  title: 'Kit/BaseInput',
  component: BaseInput,
  argTypes: {
    type: { control: 'select', options: TYPES },
    size: { control: 'select', options: SIZES },
    label: { control: 'text' },
    placeholder: { control: 'text' },
    helperText: { control: 'text' },
    error: { control: 'text' },
    disabled: { control: 'boolean' },
    readonly: { control: 'boolean' },
    required: { control: 'boolean' },
    clearable: { control: 'boolean' },
  },
  args: { label: 'Name', placeholder: 'Enter a name', modelValue: '', size: 'md', type: 'text' },
} satisfies Meta<typeof BaseInput>

export default meta
type Story = StoryObj<typeof meta>

export const Playground: Story = {}

export const WithHelper: Story = { args: { helperText: 'Shown to everyone in the workspace.' } }

export const WithError: Story = { args: { modelValue: 'nope', error: 'This value is not valid.' } }

export const Required: Story = { args: { required: true } }

export const Disabled: Story = { args: { disabled: true, modelValue: 'Locked value' } }

export const Readonly: Story = { args: { readonly: true, modelValue: 'Read-only value' } }

export const Sizes: Story = {
  render: () => ({
    components: { BaseInput },
    setup: () => ({ SIZES }),
    template: `
      <div style="display:grid;gap:0.75rem;max-width:20rem">
        <BaseInput v-for="s in SIZES" :key="s" :size="s" :label="s" :placeholder="s" />
      </div>`,
  }),
}

export const PrefixAndSuffix: Story = {
  render: () => ({
    components: { BaseInput },
    template: `
      <div style="max-width:20rem">
        <BaseInput label="Amount" placeholder="0.00">
          <template #prefix>$</template>
          <template #suffix>USD</template>
        </BaseInput>
      </div>`,
  }),
}

export const Clearable: Story = {
  args: { clearable: true, clearLabel: 'Clear', modelValue: 'Clear me' },
}
