import type { Meta, StoryObj } from '@storybook/vue3'
import LoadingOverlay from './LoadingOverlay.vue'

const meta = {
  title: 'Components/UI/LoadingOverlay',
  component: LoadingOverlay,
  argTypes: {
    loading: {
      control: 'boolean',
      description: 'Show the pulsing indicator badge on top of existing content',
    },
  },
} as Meta<typeof LoadingOverlay>

export default meta
type Story = StoryObj<any>

export const Idle: Story = {
  render: () => ({
    components: { LoadingOverlay },
    template: `
      <div class="h-64 w-96">
        <LoadingOverlay :loading="false">
          <div class="p-6 bg-white rounded border h-full">
            <h2 class="text-lg font-semibold mb-2">Sessions</h2>
            <p class="text-sm text-gray-600">3 sessions loaded. No refresh in progress.</p>
          </div>
        </LoadingOverlay>
      </div>
    `,
  }),
}

export const Refreshing: Story = {
  render: () => ({
    components: { LoadingOverlay },
    template: `
      <div class="h-64 w-96">
        <LoadingOverlay :loading="true">
          <div class="p-6 bg-white rounded border h-full">
            <h2 class="text-lg font-semibold mb-2">Sessions</h2>
            <p class="text-sm text-gray-600">3 sessions shown. A subtle indicator appears while updating.</p>
          </div>
        </LoadingOverlay>
      </div>
    `,
  }),
}
