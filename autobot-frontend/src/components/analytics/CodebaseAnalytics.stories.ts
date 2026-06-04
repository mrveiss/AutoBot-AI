import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import CodebaseAnalytics from './CodebaseAnalytics.vue';

const meta = {
  title: 'Components/Analytics/CodebaseAnalytics',
  component: CodebaseAnalytics,
  tags: ['autodocs'],
} as Meta<typeof CodebaseAnalytics>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {},
};

export const Analyzing: Story = {
  args: {},
};

export const WithResults: Story = {
  args: {},
  render: () => ({
    template: '<CodebaseAnalytics />',
    components: { CodebaseAnalytics },
  }),
};

export const Empty: Story = {
  args: {},
};
