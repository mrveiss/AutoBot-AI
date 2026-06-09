// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import LoadingBoundary from './LoadingBoundary.vue'

const meta = {
  title: 'Components/UI/LoadingBoundary',
  component: LoadingBoundary,
  argTypes: {
    loading: {
      control: 'boolean',
      description: 'Show the loading spinner, replacing slot content',
    },
    error: {
      control: 'text',
      description: 'Error message to display (takes priority over loading)',
    },
    message: {
      control: 'text',
      description: 'Message shown below the spinner while loading',
    },
    timeoutMs: {
      control: 'number',
      description: 'Milliseconds before emitting loading-timeout (0 disables)',
    },
  },
} as Meta<typeof LoadingBoundary>

export default meta
type Story = StoryObj<any>

export const Loading: Story = {
  render: () => ({
    components: { LoadingBoundary },
    template: `
      <div class="h-96">
        <LoadingBoundary :loading="true" message="Loading conversation..." />
      </div>
    `,
  }),
}

export const ErrorState: Story = {
  render: () => ({
    components: { LoadingBoundary },
    template: `
      <div class="h-96">
        <LoadingBoundary
          :loading="false"
          error="Failed to load knowledge base: backend unreachable."
        />
      </div>
    `,
  }),
}

export const ErrorWithRetry: Story = {
  render: () => ({
    components: { LoadingBoundary },
    setup() {
      return { onRetry: () => alert('retry triggered') }
    },
    template: `
      <div class="h-96">
        <LoadingBoundary
          :loading="false"
          error="Connection timed out."
          :on-retry="onRetry"
        />
      </div>
    `,
  }),
}

export const ContentLoaded: Story = {
  render: () => ({
    components: { LoadingBoundary },
    template: `
      <div class="h-96">
        <LoadingBoundary :loading="false">
          <div class="p-6">
            <h2 class="text-lg font-semibold mb-2">Conversation</h2>
            <p class="text-sm text-gray-600">All messages loaded successfully.</p>
          </div>
        </LoadingBoundary>
      </div>
    `,
  }),
}

export const CustomLoadingSlot: Story = {
  render: () => ({
    components: { LoadingBoundary },
    template: `
      <div class="h-96">
        <LoadingBoundary :loading="true">
          <template #loading-message>
            <span class="text-xs text-blue-500 font-mono">Fetching model weights…</span>
          </template>
        </LoadingBoundary>
      </div>
    `,
  }),
}

export const CustomErrorSlot: Story = {
  render: () => ({
    components: { LoadingBoundary },
    template: `
      <div class="h-96">
        <LoadingBoundary :loading="false" error="Custom error">
          <template #error-content>
            <div class="p-4 bg-red-50 rounded border border-red-200 text-sm text-red-700">
              Something went wrong. <button class="underline" @click="alert('retry')">Try again</button>
            </div>
          </template>
        </LoadingBoundary>
      </div>
    `,
  }),
}
