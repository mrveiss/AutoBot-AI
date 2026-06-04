import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import TechnicalDebtDashboard from './TechnicalDebtDashboard.vue';

const meta = {
  title: 'Components/Analytics/TechnicalDebtDashboard',
  component: TechnicalDebtDashboard,
  tags: ['autodocs'],
} as Meta<typeof TechnicalDebtDashboard>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {},
};

export const Loading: Story = {
  args: {},
};

export const WithDebtData: Story = {
  args: {},
  render: () => ({
    template: '<TechnicalDebtDashboard />',
    components: { TechnicalDebtDashboard },
  }),
};

export const HighDebt: Story = {
  args: {},
};

export const LowDebt: Story = {
  args: {},
};
