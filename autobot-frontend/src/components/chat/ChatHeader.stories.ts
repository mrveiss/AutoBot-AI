import type { Meta, StoryObj } from '@storybook/vue3';
import ChatHeader from './ChatHeader.vue';

const meta = {
  title: 'Components/Chat/ChatHeader',
  component: ChatHeader,
  tags: ['autodocs'],
  argTypes: {
    currentSessionTitle: {
      control: 'text',
      description: 'Title of current chat session',
    },
    currentSessionId: {
      control: 'text',
      description: 'ID of current session',
    },
    sessionInfo: {
      control: 'text',
      description: 'Additional session information',
    },
    connectionStatus: {
      control: 'select',
      options: ['Connected', 'Connecting', 'Disconnected'],
      description: 'Connection status text',
    },
  },
} satisfies Meta<typeof ChatHeader>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    currentSessionTitle: 'Chat with Assistant',
    currentSessionId: 'session-123',
    sessionInfo: 'Active chat session',
    connectionStatus: 'Connected',
  },
};

export const Connecting: Story = {
  args: {
    currentSessionTitle: 'Chat with Assistant',
    currentSessionId: 'session-123',
    sessionInfo: 'Establishing connection...',
    connectionStatus: 'Connecting',
  },
};

export const Disconnected: Story = {
  args: {
    currentSessionTitle: 'Chat with Assistant',
    currentSessionId: 'session-123',
    sessionInfo: 'Connection lost',
    connectionStatus: 'Disconnected',
  },
};

export const NoSession: Story = {
  args: {
    currentSessionTitle: 'New Chat',
    currentSessionId: '',
    sessionInfo: 'Start a new conversation',
    connectionStatus: 'Connected',
  },
};

export const WithLongTitle: Story = {
  args: {
    currentSessionTitle: 'This is a very long chat session title that might wrap',
    currentSessionId: 'session-456',
    sessionInfo: 'Session started 5 minutes ago',
    connectionStatus: 'Connected',
  },
};
