import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import CodebaseAnalyticsLanding from './CodebaseAnalyticsLanding.vue';

const meta = {
  title: 'Components/Analytics/CodebaseAnalyticsLanding',
  component: CodebaseAnalyticsLanding,
  tags: ['autodocs'],
} as Meta<typeof CodebaseAnalyticsLanding>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {},
};

export const Loading: Story = {
  args: {},
  render: () => ({
    template: '<CodebaseAnalyticsLanding />',
    components: { CodebaseAnalyticsLanding },
  }),
};

export const WithProjects: Story = {
  args: {},
};

export const Empty: Story = {
  args: {},
};
