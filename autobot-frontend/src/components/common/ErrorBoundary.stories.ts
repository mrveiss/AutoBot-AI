import type { Meta, StoryObj } from '@storybook/vue3';
import ErrorBoundary from './ErrorBoundary.vue';

const meta = {
  title: 'Components/Common/ErrorBoundary',
  component: ErrorBoundary,
  argTypes: {
    title: {
      control: 'text',
      description: 'Error title',
    },
    message: {
      control: 'text',
      description: 'Error message',
    },
    retryable: {
      control: 'boolean',
      description: 'Show retry button',
    },
  },
} as Meta<typeof ErrorBoundary>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    title: 'Something went wrong',
    message: 'An unexpected error occurred. Please try again.',
  },
  render: (args: any) => ({
    components: { ErrorBoundary },
    setup() {
      return { args };
    },
    template: `
      <ErrorBoundary v-bind="args">
        <div class="p-4 bg-green-100 text-green-800">
          This is protected content that would show if no error occurred.
        </div>
      </ErrorBoundary>
    `,
  }),
};

export const Retryable: Story = {
  args: {
    title: 'Failed to load data',
    message: 'The data could not be loaded. Click retry to try again.',
    retryable: true,
  },
  render: (args: any) => ({
    components: { ErrorBoundary },
    setup() {
      return { args };
    },
    template: `
      <ErrorBoundary v-bind="args" @retry="() => alert('Retry clicked')">
        <div class="p-4 bg-green-100 text-green-800">
          Protected content area
        </div>
      </ErrorBoundary>
    `,
  }),
};

export const WithContent: Story = {
  render: () => ({
    components: { ErrorBoundary },
    template: `
      <ErrorBoundary title="Error occurred" message="An error occurred while rendering the content">
        <div class="space-y-4">
          <div class="p-4 bg-blue-100 text-blue-800 rounded">
            This is some protected content
          </div>
          <div class="p-4 bg-blue-100 text-blue-800 rounded">
            More protected content
          </div>
        </div>
      </ErrorBoundary>
    `,
  }),
};
