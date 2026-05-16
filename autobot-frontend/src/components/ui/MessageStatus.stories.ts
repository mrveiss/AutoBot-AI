import type { Meta, StoryObj } from '@storybook/vue3';
import MessageStatus from './MessageStatus.vue';

const meta = {
  title: 'Components/UI/MessageStatus',
  component: MessageStatus,
  argTypes: {
    status: {
      control: 'select',
      options: ['sending', 'sent', 'delivered', 'read', 'failed', 'queued', 'retrying'],
      description: 'Current message delivery status',
    },
    showText: {
      control: 'boolean',
      description: 'Show status text alongside the icon',
    },
    allowRetry: {
      control: 'boolean',
      description: 'Show retry button when status is failed',
    },
    timestamp: {
      control: 'date',
      description: 'Time the status was reached (used in tooltip)',
    },
    error: {
      control: 'text',
      description: 'Error description shown in tooltip when status is failed',
    },
  },
} as Meta<typeof MessageStatus>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Sending: Story = {
  args: {
    status: 'sending',
    showText: true,
  },
};

export const Sent: Story = {
  args: {
    status: 'sent',
    showText: true,
  },
};

export const Delivered: Story = {
  args: {
    status: 'delivered',
    showText: true,
  },
};

export const Read: Story = {
  args: {
    status: 'read',
    showText: true,
  },
};

export const Failed: Story = {
  args: {
    status: 'failed',
    showText: true,
    allowRetry: true,
    error: 'Network error: connection refused',
  },
};

export const Queued: Story = {
  args: {
    status: 'queued',
    showText: true,
  },
};

export const Retrying: Story = {
  args: {
    status: 'retrying',
    showText: true,
  },
};

export const IconOnly: Story = {
  args: {
    status: 'delivered',
    showText: false,
  },
};

export const AllStates: Story = {
  render: () => ({
    components: { MessageStatus },
    template: `
      <div class="flex flex-col gap-3">
        <MessageStatus status="sending" :show-text="true" />
        <MessageStatus status="sent" :show-text="true" />
        <MessageStatus status="delivered" :show-text="true" />
        <MessageStatus status="read" :show-text="true" />
        <MessageStatus status="queued" :show-text="true" />
        <MessageStatus status="retrying" :show-text="true" />
        <MessageStatus status="failed" :show-text="true" :allow-retry="true" error="Timeout after 30s" />
      </div>
    `,
  }),
};
