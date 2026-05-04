import type { Meta, StoryObj } from '@storybook/vue3';
import HostSelector from './HostSelector.vue';

const meta = {
  title: 'Components/UI/HostSelector',
  component: HostSelector,
  tags: ['autodocs'],
  argTypes: {
    chatId: {
      control: 'text',
      description: 'Chat session ID used to scope host preferences',
    },
    requiredCapability: {
      control: 'select',
      options: [undefined, 'ssh', 'vnc'],
      description: 'Filter hosts to only those with this capability',
    },
    modelValue: {
      control: 'object',
      description: 'v-model: currently selected host (or null)',
    },
  },
} satisfies Meta<typeof HostSelector>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    modelValue: null,
  },
};

export const SshOnly: Story = {
  args: {
    modelValue: null,
    requiredCapability: 'ssh',
  },
};

export const VncOnly: Story = {
  args: {
    modelValue: null,
    requiredCapability: 'vnc',
  },
};

export const WithChatContext: Story = {
  args: {
    modelValue: null,
    chatId: 'chat-123',
  },
};

export const Preselected: Story = {
  args: {
    modelValue: {
      id: 'host-1',
      name: 'Backend VM',
      host: '172.16.168.20',
      ssh_port: 22,
      capabilities: ['ssh'],
      os: 'Ubuntu 24.04',
    },
  },
};
