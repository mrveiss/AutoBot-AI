import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import ConversationFlowDashboard from './ConversationFlowDashboard.vue';

const meta = {
  title: 'Components/Analytics/ConversationFlowDashboard',
  component: ConversationFlowDashboard,
  tags: ['autodocs'],
} as Meta<typeof ConversationFlowDashboard>;

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
    template: '<ConversationFlowDashboard />',
    components: { ConversationFlowDashboard },
  }),
};

export const Last7Days: Story = {
  args: {},
};
