import type { Meta, StoryObj } from '@storybook/vue3';
import NotificationConfigModal from './NotificationConfigModal.vue';

const meta = {
  title: 'Components/Workflow/NotificationConfigModal',
  component: NotificationConfigModal,
  tags: ['autodocs'],
  argTypes: {
    visible: {
      control: 'boolean',
      description: 'Whether the modal is visible',
    },
    workflowId: {
      control: 'text',
      description: 'ID of the workflow to configure notifications for',
    },
  },
} as Meta<typeof NotificationConfigModal>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Visible: Story = {
  args: {
    visible: true,
    workflowId: 'wf-abc123',
  },
};

export const Hidden: Story = {
  args: {
    visible: false,
    workflowId: 'wf-abc123',
  },
};

export const DifferentWorkflow: Story = {
  args: {
    visible: true,
    workflowId: 'wf-xyz789',
  },
};
