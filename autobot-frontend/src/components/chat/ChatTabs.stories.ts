import type { Meta } from '@storybook/vue3';
import ChatTabs from './ChatTabs.vue';

const meta = {
  title: 'Components/Chat/ChatTabs',
  component: ChatTabs,
  tags: ['autodocs'],
  argTypes: {
    activeTab: {
      control: 'select',
      options: ['chat', 'files', 'terminal', 'browser', 'novnc'],
      description: 'Currently active tab key',
    },
  },
} as Meta<typeof ChatTabs>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<any>;

export const ChatActive: Story = {
  args: {
    activeTab: 'chat',
  },
};

export const TerminalActive: Story = {
  args: {
    activeTab: 'terminal',
  },
};

export const FilesActive: Story = {
  args: {
    activeTab: 'files',
  },
};

export const CustomTabs: Story = {
  args: {
    activeTab: 'chat',
    tabs: [
      { key: 'chat', label: 'Chat', icon: 'fas fa-comments' },
      { key: 'terminal', label: 'Terminal', icon: 'fas fa-terminal' },
    ],
  },
};
