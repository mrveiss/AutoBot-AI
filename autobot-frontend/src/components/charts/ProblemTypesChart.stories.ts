import type { Meta } from '@storybook/vue3';
import ProblemTypesChart from './ProblemTypesChart.vue';

const meta = {
  title: 'Components/Charts/ProblemTypesChart',
  component: ProblemTypesChart,
  tags: ['autodocs'],
  argTypes: {
    title: {
      control: 'text',
      description: 'Chart title (overrides i18n default)',
    },
    subtitle: {
      control: 'text',
      description: 'Chart subtitle',
    },
    height: {
      control: 'number',
      description: 'Chart height in pixels',
    },
    loading: {
      control: 'boolean',
      description: 'Show loading state',
    },
    error: {
      control: 'text',
      description: 'Error message to display',
    },
  },
} as Meta<typeof ProblemTypesChart>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<any>;

const sampleData = [
  { type: 'security', count: 23 },
  { type: 'race_condition', count: 18 },
  { type: 'performance', count: 42 },
  { type: 'style', count: 67 },
  { type: 'complexity', count: 31 },
  { type: 'documentation', count: 15 },
];

export const Default: Story = {
  args: {
    data: sampleData,
    height: 350,
  },
};

export const WithCustomTitle: Story = {
  args: {
    data: sampleData,
    title: 'Problem Type Breakdown',
    subtitle: 'Distribution of detected issues by category',
    height: 350,
  },
};

export const NameValueFormat: Story = {
  args: {
    data: [
      { name: 'Error', value: 12 },
      { name: 'Warning', value: 45 },
      { name: 'Info', value: 89 },
      { name: 'Hint', value: 24 },
    ],
    title: 'Issues by Severity Level',
    height: 350,
  },
};

export const LoadingState: Story = {
  args: {
    data: [],
    loading: true,
    height: 350,
  },
};

export const ErrorState: Story = {
  args: {
    data: [],
    error: 'Failed to load problem type data.',
    height: 350,
  },
};
