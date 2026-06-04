import type { Meta } from '@storybook/vue3';
import ChatInterface from './ChatInterface.vue';

const meta = {
  title: 'Components/Chat/ChatInterface',
  component: ChatInterface,
  tags: ['autodocs'],
  parameters: {
    layout: 'fullscreen',
  },
} as Meta<typeof ChatInterface>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<any>;

export const Default: Story = {
  render: () => ({
    components: { ChatInterface },
    template: `<div style="height:100vh; width:100%;"><ChatInterface /></div>`,
  }),
};

export const Contained: Story = {
  render: () => ({
    components: { ChatInterface },
    template: `<div style="height:700px; width:1100px; overflow:hidden;"><ChatInterface /></div>`,
  }),
};
