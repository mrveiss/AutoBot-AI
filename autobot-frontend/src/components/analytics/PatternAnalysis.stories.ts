import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import PatternAnalysis from './PatternAnalysis.vue';

const meta = {
  title: 'Components/Analytics/PatternAnalysis',
  component: PatternAnalysis,
  tags: ['autodocs'],
  argTypes: {
    rootPath: { control: 'text' },
    autoLoad: { control: 'boolean' },
  },
} as Meta<typeof PatternAnalysis>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    rootPath: '/opt/autobot',
    autoLoad: false,
  },
};

export const AutoLoad: Story = {
  args: {
    rootPath: '/opt/autobot',
    autoLoad: true,
  },
};

export const NoPath: Story = {
  args: {
    rootPath: '',
    autoLoad: false,
  },
};

export const LongPath: Story = {
  args: {
    rootPath: '/home/user/projects/very-long-project-name/autobot-ai',
    autoLoad: false,
  },
};
