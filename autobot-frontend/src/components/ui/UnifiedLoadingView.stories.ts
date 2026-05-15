import type { Meta, StoryObj } from '@storybook/vue3';
import UnifiedLoadingView from './UnifiedLoadingView.vue';

const meta = {
  title: 'Components/UI/UnifiedLoadingView',
  component: UnifiedLoadingView,
  tags: ['autodocs'],
  argTypes: {
    isLoading: {
      control: 'boolean',
      description: 'Whether to show the loading state',
    },
    error: {
      control: 'text',
      description: 'Error message to display (overrides loading)',
    },
    message: {
      control: 'text',
      description: 'Loading message shown below the spinner',
    },
    hasTimedOut: {
      control: 'boolean',
      description: 'Show "taking longer than expected" warning',
    },
    hasContent: {
      control: 'boolean',
      description: 'Whether the slot already has content (uses subtle indicator)',
    },
    timeoutMs: {
      control: 'number',
      description: 'Milliseconds before timing out (0 disables)',
    },
  },
} as Meta<typeof UnifiedLoadingView>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Loading: Story = {
  render: () => ({
    components: { UnifiedLoadingView },
    template: `
      <div class="h-96">
        <UnifiedLoadingView :is-loading="true" :has-content="false" message="Loading conversation..." />
      </div>
    `,
  }),
};

export const LoadingTimeout: Story = {
  render: () => ({
    components: { UnifiedLoadingView },
    template: `
      <div class="h-96">
        <UnifiedLoadingView
          :is-loading="true"
          :has-content="false"
          :has-timed-out="true"
          message="Loading large model..."
        />
      </div>
    `,
  }),
};

export const ErrorState: Story = {
  render: () => ({
    components: { UnifiedLoadingView },
    template: `
      <div class="h-96">
        <UnifiedLoadingView
          :is-loading="false"
          error="Failed to load knowledge base: backend unreachable."
        />
      </div>
    `,
  }),
};

export const ContentLoaded: Story = {
  render: () => ({
    components: { UnifiedLoadingView },
    template: `
      <div class="h-96">
        <UnifiedLoadingView :is-loading="false" :has-content="true">
          <div class="p-6">
            <h2 class="text-lg font-semibold mb-2">Conversation</h2>
            <p class="text-sm text-gray-600">All messages loaded successfully.</p>
          </div>
        </UnifiedLoadingView>
      </div>
    `,
  }),
};

export const ContentRefreshing: Story = {
  render: () => ({
    components: { UnifiedLoadingView },
    template: `
      <div class="h-96">
        <UnifiedLoadingView :is-loading="true" :has-content="true">
          <div class="p-6">
            <h2 class="text-lg font-semibold mb-2">Existing content</h2>
            <p class="text-sm text-gray-600">A subtle indicator shows in the corner while we update.</p>
          </div>
        </UnifiedLoadingView>
      </div>
    `,
  }),
};
