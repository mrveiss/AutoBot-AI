import type { Meta } from '@storybook/vue3';
import OperationProgress from './OperationProgress.vue';

const meta = {
  title: 'Components/Operations/OperationProgress',
  component: OperationProgress,
  tags: ['autodocs'],
  argTypes: {
    progress: {
      control: { type: 'range', min: 0, max: 100, step: 1 },
      description: 'Progress percentage (0–100)',
    },
    status: {
      control: 'select',
      options: ['pending', 'running', 'completed', 'failed', 'timeout', 'cancelled', 'paused'],
      description: 'Operation status — drives bar colour and step icon',
    },
    processedItems: {
      control: 'number',
      description: 'Number of items already processed',
    },
    estimatedItems: {
      control: 'number',
      description: 'Total estimated items',
    },
    currentStep: {
      control: 'text',
      description: 'Human-readable current step label',
    },
    size: {
      control: 'select',
      options: ['sm', 'md', 'lg'],
      description: 'Bar height variant',
    },
    showInfo: {
      control: 'boolean',
      description: 'Show percentage and item counts below the bar',
    },
    showItems: {
      control: 'boolean',
      description: 'Show processed/estimated item counts',
    },
    showStep: {
      control: 'boolean',
      description: 'Show the current step label',
    },
  },
} as Meta<typeof OperationProgress>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = import('@storybook/vue3').StoryObj<any>;

export const Running: Story = {
  args: {
    progress: 42,
    status: 'running',
    processedItems: 420,
    estimatedItems: 1000,
    currentStep: 'Indexing documents…',
    size: 'md',
    showInfo: true,
    showItems: true,
    showStep: true,
  },
};

export const Completed: Story = {
  args: {
    progress: 100,
    status: 'completed',
    processedItems: 1000,
    estimatedItems: 1000,
    currentStep: '',
    size: 'md',
    showInfo: true,
    showItems: true,
    showStep: false,
  },
};

export const Failed: Story = {
  args: {
    progress: 68,
    status: 'failed',
    processedItems: 680,
    estimatedItems: 1000,
    currentStep: 'Processing batch 7',
    size: 'md',
    showInfo: true,
    showItems: true,
    showStep: true,
  },
};

export const Paused: Story = {
  args: {
    progress: 55,
    status: 'paused',
    processedItems: 550,
    estimatedItems: 1000,
    currentStep: 'Awaiting resume',
    size: 'md',
    showInfo: true,
    showItems: true,
    showStep: true,
  },
};

export const SmallBarNoInfo: Story = {
  args: {
    progress: 30,
    status: 'running',
    size: 'sm',
    showInfo: false,
    showItems: false,
    showStep: false,
  },
};

export const LargeBar: Story = {
  args: {
    progress: 75,
    status: 'running',
    processedItems: 750,
    estimatedItems: 1000,
    currentStep: 'Generating embeddings…',
    size: 'lg',
    showInfo: true,
    showItems: true,
    showStep: true,
  },
};

export const AllSizes: Story = {
  render: () => ({
    components: { OperationProgress },
    template: `
      <div style="display:flex;flex-direction:column;gap:16px;padding:16px;max-width:400px">
        <div>
          <p style="margin:0 0 4px;font-size:12px;color:#6b7280">Small</p>
          <OperationProgress :progress="60" status="running" size="sm" :show-info="false" :show-step="false" />
        </div>
        <div>
          <p style="margin:0 0 4px;font-size:12px;color:#6b7280">Medium</p>
          <OperationProgress :progress="60" status="running" size="md" :show-info="true" :show-step="false" />
        </div>
        <div>
          <p style="margin:0 0 4px;font-size:12px;color:#6b7280">Large</p>
          <OperationProgress :progress="60" status="running" size="lg" :show-info="true" current-step="Processing…" />
        </div>
      </div>
    `,
  }),
};
