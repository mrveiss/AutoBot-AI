import type { Meta } from '@storybook/vue3';
import ChatBrowser from './ChatBrowser.vue';

const meta = {
  title: 'Components/Chat/ChatBrowser',
  component: ChatBrowser,
  tags: ['autodocs'],
  argTypes: {
    chatSessionId: {
      control: 'text',
      description: 'Chat session ID used to look up a browser session',
    },
    autoConnect: {
      control: 'boolean',
      description: 'Whether to auto-connect the browser session on mount',
    },
  },
} as Meta<typeof ChatBrowser>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<any>;

export const WithSession: Story = {
  args: {
    chatSessionId: 'session-demo-001',
    autoConnect: false,
  },
};

export const NoSession: Story = {
  args: {
    chatSessionId: null,
    autoConnect: false,
  },
};

export const AutoConnect: Story = {
  args: {
    chatSessionId: 'session-demo-002',
    autoConnect: true,
  },
};
