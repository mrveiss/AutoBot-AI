// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import { ref } from 'vue'
import BaseFormField from './BaseFormField.vue'
import BaseInput from './BaseInput.vue'

const meta = {
  title: 'Kit/BaseFormField',
  component: BaseFormField,
  argTypes: {
    required: { control: 'boolean' },
    hint: { control: 'text' },
    error: { control: 'text' },
  },
} as Meta<typeof BaseFormField>

export default meta
type Story = StoryObj<Record<string, unknown>>

const render = (args: Record<string, unknown>) => ({
  components: { BaseFormField, BaseInput },
  setup: () => ({ args, value: ref('') }),
  template: `<BaseFormField v-bind="args" label="Repository" v-slot="{ id, describedBy, invalid, required }">
    <input :id="id" v-model="value" :aria-describedby="describedBy" :aria-invalid="invalid" :required="required" />
  </BaseFormField>`,
})

export const Plain: Story = { args: {}, render }
export const WithHint: Story = { args: { hint: 'owner/name, for example acme/app' }, render }
export const Required: Story = { args: { required: true }, render }
export const WithError: Story = { args: { required: true, error: 'Repository is required' }, render }
