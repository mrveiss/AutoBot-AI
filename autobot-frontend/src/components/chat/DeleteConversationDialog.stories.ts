import type { Meta } from '@storybook/vue3';
import DeleteConversationDialog from './DeleteConversationDialog.vue';

const meta = {
  title: 'Components/Chat/DeleteConversationDialog',
  component: DeleteConversationDialog,
  tags: ['autodocs'],
  argTypes: {
    visible: {
      control: 'boolean',
      description: 'Controls dialog visibility (v-model)',
    },
    sessionId: {
      control: 'text',
      description: 'ID of the session to delete',
    },
    sessionName: {
      control: 'text',
      description: 'Display name of the session',
    },
    kbFactsLoading: {
      control: 'boolean',
      description: 'Whether KB facts are loading',
    },
  },
} as Meta<typeof DeleteConversationDialog>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<any>;

export const Visible: Story = {
  args: {
    visible: true,
    sessionId: 'session-del-001',
    sessionName: 'Weekly Planning Session',
    fileStats: null,
    kbFacts: null,
    kbFactsLoading: false,
  },
};

export const WithFileStats: Story = {
  args: {
    visible: true,
    sessionId: 'session-del-002',
    sessionName: 'Research Session',
    fileStats: { total_files: 5, total_size_bytes: 1048576, oldest_file: null, newest_file: null },
    kbFacts: null,
    kbFactsLoading: false,
  },
};

export const Hidden: Story = {
  args: {
    visible: false,
    sessionId: 'session-del-003',
    sessionName: 'Hidden Dialog',
    fileStats: null,
    kbFacts: null,
    kbFactsLoading: false,
  },
};
