import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import LLMPatternDashboard from './LLMPatternDashboard.vue';

const meta = {
  title: 'Components/Analytics/LLMPatternDashboard',
  component: LLMPatternDashboard,
  tags: ['autodocs'],
} as Meta<typeof LLMPatternDashboard>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {},
};

export const Loading: Story = {
  args: {},
};

export const WithData: Story = {
  args: {},
  render: () => ({
    template: '<LLMPatternDashboard />',
    components: { LLMPatternDashboard },
  }),
};

export const Empty: Story = {
  args: {},
};
