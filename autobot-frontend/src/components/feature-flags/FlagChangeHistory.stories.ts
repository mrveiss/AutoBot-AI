import type { Meta, StoryObj } from '@storybook/vue3';
import FlagChangeHistory from './FlagChangeHistory.vue';

const meta = {
  title: 'Components/FeatureFlags/FlagChangeHistory',
  component: FlagChangeHistory,
  tags: ['autodocs'],
  argTypes: {
    history: {
      control: 'object',
      description: 'Array of HistoryEntry objects (timestamp, mode, changed_by)',
    },
    loading: {
      control: 'boolean',
      description: 'Show loading state when history is not yet fetched',
    },
  },
} as Meta<typeof FlagChangeHistory>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

const now = new Date();
const hoursAgo = (h: number) => new Date(now.getTime() - h * 3600 * 1000).toISOString();

export const WithHistory: Story = {
  args: {
    history: [
      { timestamp: hoursAgo(1), mode: 'enforced', changed_by: 'alice@example.com' },
      { timestamp: hoursAgo(6), mode: 'log_only', changed_by: 'bob@example.com' },
      { timestamp: hoursAgo(24), mode: 'disabled', changed_by: 'system' },
      { timestamp: hoursAgo(72), mode: 'log_only', changed_by: 'charlie@example.com' },
    ],
    loading: false,
  },
};

export const Empty: Story = {
  args: {
    history: [],
    loading: false,
  },
};

export const Loading: Story = {
  args: {
    history: [],
    loading: true,
  },
};

export const SingleEntry: Story = {
  args: {
    history: [
      { timestamp: hoursAgo(2), mode: 'enforced', changed_by: 'admin@example.com' },
    ],
    loading: false,
  },
};

export const LongHistory: Story = {
  args: {
    history: [
      { timestamp: hoursAgo(0.5), mode: 'enforced', changed_by: 'alice@example.com' },
      { timestamp: hoursAgo(3), mode: 'log_only', changed_by: 'alice@example.com' },
      { timestamp: hoursAgo(8), mode: 'enforced', changed_by: 'bob@example.com' },
      { timestamp: hoursAgo(15), mode: 'disabled', changed_by: 'system' },
      { timestamp: hoursAgo(30), mode: 'log_only', changed_by: 'charlie@example.com' },
      { timestamp: hoursAgo(48), mode: 'disabled', changed_by: 'alice@example.com' },
      { timestamp: hoursAgo(96), mode: 'log_only', changed_by: 'system' },
    ],
    loading: false,
  },
};
