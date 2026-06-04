import type { Meta, StoryObj } from '@storybook/vue3';
import ProgressBar from './ProgressBar.vue';

const meta = {
  title: 'Components/UI/ProgressBar',
  component: ProgressBar,
  argTypes: {
    progress: {
      control: { type: 'range', min: 0, max: 100, step: 1 },
      description: 'Current progress (0-100)',
    },
    variant: {
      control: 'select',
      options: ['default', 'success', 'warning', 'error', 'info'],
      description: 'Color variant',
    },
    size: {
      control: 'select',
      options: ['xs', 'sm', 'md', 'lg'],
      description: 'Bar height',
    },
    animated: {
      control: 'boolean',
      description: 'Animate width changes and shimmer overlay',
    },
    indeterminate: {
      control: 'boolean',
      description: 'Show indeterminate (looping) animation',
    },
    label: {
      control: 'text',
      description: 'Label shown above the bar',
    },
    showLabel: {
      control: 'boolean',
      description: 'Show label row',
    },
    showPercentage: {
      control: 'boolean',
      description: 'Show percentage in label row',
    },
    showDetails: {
      control: 'boolean',
      description: 'Show details row (current/total + ETA)',
    },
    current: {
      control: 'number',
      description: 'Current bytes (when showing transfer details)',
    },
    total: {
      control: 'number',
      description: 'Total bytes (when showing transfer details)',
    },
    eta: {
      control: 'number',
      description: 'Estimated seconds remaining',
    },
    rounded: {
      control: 'boolean',
      description: 'Use rounded corners on the bar',
    },
  },
} as Meta<typeof ProgressBar>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    progress: 45,
  },
};

export const Success: Story = {
  args: {
    progress: 100,
    variant: 'success',
    label: 'Upload complete',
    showLabel: true,
  },
};

export const Warning: Story = {
  args: {
    progress: 80,
    variant: 'warning',
    label: 'Disk usage',
    showLabel: true,
  },
};

export const Error: Story = {
  args: {
    progress: 30,
    variant: 'error',
    label: 'Failed at',
    showLabel: true,
  },
};

export const Info: Story = {
  args: {
    progress: 60,
    variant: 'info',
    label: 'Indexing knowledge base',
    showLabel: true,
  },
};

export const Indeterminate: Story = {
  args: {
    progress: 0,
    indeterminate: true,
    label: 'Connecting...',
    showLabel: true,
    showPercentage: false,
  },
};

export const FileTransfer: Story = {
  args: {
    progress: 65,
    variant: 'info',
    label: 'Uploading model.safetensors',
    showLabel: true,
    showDetails: true,
    current: 6_500_000_000,
    total: 10_000_000_000,
    eta: 124,
  },
};

export const AllSizes: Story = {
  render: () => ({
    components: { ProgressBar },
    template: `
      <div class="flex flex-col gap-4 max-w-md">
        <ProgressBar :progress="60" size="xs" />
        <ProgressBar :progress="60" size="sm" />
        <ProgressBar :progress="60" size="md" />
        <ProgressBar :progress="60" size="lg" />
      </div>
    `,
  }),
};

export const AllVariants: Story = {
  render: () => ({
    components: { ProgressBar },
    template: `
      <div class="flex flex-col gap-4 max-w-md">
        <ProgressBar :progress="50" variant="default" label="Default" :show-label="true" />
        <ProgressBar :progress="100" variant="success" label="Success" :show-label="true" />
        <ProgressBar :progress="75" variant="warning" label="Warning" :show-label="true" />
        <ProgressBar :progress="40" variant="error" label="Error" :show-label="true" />
        <ProgressBar :progress="60" variant="info" label="Info" :show-label="true" />
      </div>
    `,
  }),
};
