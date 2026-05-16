import type { Meta } from '@storybook/vue3';
import PatternEvolutionChart from './PatternEvolutionChart.vue';

const meta = {
  title: 'Components/Charts/PatternEvolutionChart',
  component: PatternEvolutionChart,
  tags: ['autodocs'],
  argTypes: {
    title: {
      control: 'text',
      description: 'Chart title (overrides i18n default)',
    },
    subtitle: {
      control: 'text',
      description: 'Chart subtitle (overrides i18n default)',
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
} as Meta<typeof PatternEvolutionChart>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<any>;

function makeDays(count: number) {
  const now = Date.now();
  return Array.from({ length: count }, (_, i) => {
    const d = new Date(now - (count - 1 - i) * 86400000);
    return d.toISOString();
  });
}

const timestamps = makeDays(10);

const sampleData = {
  race_condition: timestamps.map((timestamp, i) => ({
    timestamp,
    count: Math.max(0, 8 - i + Math.round(Math.sin(i) * 2)),
    pattern_type: 'race_condition',
  })),
  global_state: timestamps.map((timestamp, i) => ({
    timestamp,
    count: Math.max(0, 12 - i * 0.5 + Math.round(Math.cos(i) * 1)),
    pattern_type: 'global_state',
  })),
  long_method: timestamps.map((timestamp, i) => ({
    timestamp,
    count: Math.max(0, 6 - i * 0.3),
    pattern_type: 'long_method',
  })),
};

export const Default: Story = {
  args: {
    data: sampleData,
    height: 400,
  },
};

export const WithCustomTitle: Story = {
  args: {
    data: sampleData,
    title: 'Anti-Pattern Trends',
    subtitle: 'Pattern occurrences over the last 10 days',
    height: 400,
  },
};

export const SinglePattern: Story = {
  args: {
    data: {
      race_condition: sampleData.race_condition,
    },
    title: 'Race Condition Trend',
    height: 350,
  },
};

export const LoadingState: Story = {
  args: {
    data: {},
    loading: true,
    height: 400,
  },
};

export const EmptyData: Story = {
  args: {
    data: {},
    title: 'No Pattern Data',
    height: 400,
  },
};
