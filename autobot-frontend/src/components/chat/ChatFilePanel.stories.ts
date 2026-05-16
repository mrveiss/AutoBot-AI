import type { Meta } from '@storybook/vue3';
import ChatFilePanel from './ChatFilePanel.vue';

const meta = {
  title: 'Components/Chat/ChatFilePanel',
  component: ChatFilePanel,
  tags: ['autodocs'],
  argTypes: {
    sessionId: {
      control: 'text',
      description: 'Chat session ID for file operations',
    },
  },
} as Meta<typeof ChatFilePanel>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    sessionId: 'session-file-001',
  },
  render: (args: any) => ({
    components: { ChatFilePanel },
    setup() { return { args }; },
    template: `<div style="height:600px; width:320px;"><ChatFilePanel v-bind="args" /></div>`,
  }),
};

export const DifferentSession: Story = {
  args: {
    sessionId: 'session-file-002',
  },
  render: (args: any) => ({
    components: { ChatFilePanel },
    setup() { return { args }; },
    template: `<div style="height:600px; width:320px;"><ChatFilePanel v-bind="args" /></div>`,
  }),
};
