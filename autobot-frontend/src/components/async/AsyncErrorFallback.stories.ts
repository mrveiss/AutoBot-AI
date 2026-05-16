import type { Meta, StoryObj } from '@storybook/vue3';
import AsyncErrorFallback from './AsyncErrorFallback.vue';

const meta = {
  title: 'Components/Async/AsyncErrorFallback',
  component: AsyncErrorFallback,
  tags: ['autodocs'],
  argTypes: {
    error: {
      control: 'object',
      description: 'The error object that caused the component load failure',
    },
    componentName: {
      control: 'text',
      description: 'Name of the component that failed to load',
    },
    retryCount: {
      control: { type: 'number', min: 0, max: 10 },
      description: 'How many retries have been attempted so far',
    },
    maxRetries: {
      control: { type: 'number', min: 1, max: 10 },
      description: 'Maximum number of retries allowed before giving up',
    },
  },
} as Meta<typeof AsyncErrorFallback>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    error: new Error('ChunkLoadError: Loading chunk 42 failed.'),
    componentName: 'DashboardPanel',
    retryCount: 1,
    maxRetries: 3,
  },
};

export const FirstFailure: Story = {
  args: {
    error: new Error('Failed to fetch'),
    componentName: 'KnowledgeViewer',
    retryCount: 0,
    maxRetries: 3,
  },
};

export const NoMoreRetries: Story = {
  args: {
    error: new Error('NetworkError: Network connection failed while loading the component.'),
    componentName: 'WorkflowDashboard',
    retryCount: 3,
    maxRetries: 3,
  },
};

export const WithStack: Story = {
  args: {
    error: Object.assign(new Error('timeout: The component took too long to load.'), {
      stack: [
        'Error: timeout: The component took too long to load.',
        '    at loadComponent (AsyncComponentWrapper.vue:125)',
        '    at async Promise.all (index 0)',
        '    at async setup (AsyncComponentWrapper.vue:236)',
      ].join('\n'),
    }),
    componentName: 'TerminalView',
    retryCount: 2,
    maxRetries: 3,
  },
};

export const NoError: Story = {
  args: {
    error: undefined,
    componentName: 'SettingsPanel',
    retryCount: 0,
    maxRetries: 3,
  },
};
