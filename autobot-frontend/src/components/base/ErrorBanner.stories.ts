// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import ErrorBanner from './ErrorBanner.vue'

const meta = {
  title: 'Components/Base/ErrorBanner',
  component: ErrorBanner,
  tags: ['autodocs'],
  argTypes: {
    message: {
      control: 'text',
      description: 'Banner message text'
    },
    variant: {
      control: 'select',
      options: ['error', 'warning', 'info'],
      description: 'Banner variant determining icon and color'
    },
    dismissible: {
      control: 'boolean',
      description: 'Whether the banner can be dismissed'
    },
    dismiss: {
      action: 'dismissed'
    }
  }
} satisfies Meta<typeof ErrorBanner>

export default meta
type Story = StoryObj<typeof meta>

export const Error: Story = {
  args: {
    message: 'An error occurred while processing your request. Please try again.',
    variant: 'error',
    dismissible: true
  }
}

export const Warning: Story = {
  args: {
    message: 'This action may have unintended consequences. Proceed with caution.',
    variant: 'warning',
    dismissible: true
  }
}

export const Info: Story = {
  args: {
    message: 'Your changes have been saved successfully.',
    variant: 'info',
    dismissible: true
  }
}

export const Undismissible: Story = {
  args: {
    message: 'This is a critical error that cannot be dismissed.',
    variant: 'error',
    dismissible: false
  }
}

export const WithSlot: Story = {
  render: (args) => ({
    components: { ErrorBanner },
    setup() {
      return { args }
    },
    template: `
      <ErrorBanner v-bind="args">
        <strong>Custom error message:</strong> This banner uses a slot for complex content.
      </ErrorBanner>
    `
  })
}

export const LongMessage: Story = {
  args: {
    message: `Operation failed: The requested resource could not be processed due to a validation error. Please ensure all required fields are completed and try again. If the problem persists, contact support.`,
    variant: 'error',
    dismissible: true
  }
}
