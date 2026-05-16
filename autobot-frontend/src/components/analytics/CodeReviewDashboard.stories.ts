import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import CodeReviewDashboard from './CodeReviewDashboard.vue';

const meta = {
  title: 'Components/Analytics/CodeReviewDashboard',
  component: CodeReviewDashboard,
  tags: ['autodocs'],
} as Meta<typeof CodeReviewDashboard>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {},
};

export const Loading: Story = {
  args: {},
};

export const WithResults: Story = {
  args: {},
  render: () => ({
    template: '<CodeReviewDashboard />',
    components: { CodeReviewDashboard },
  }),
};

export const Empty: Story = {
  args: {},
};
